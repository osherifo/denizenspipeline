"""fmriprep backend — wraps fmriprep (bare install, Singularity, or Docker)."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from pathlib import Path

from fmriflow.preproc.backends import register_backend
from fmriflow.preproc.backends.fmriprep_params import FmriprepParams
from fmriflow.preproc.errors import BackendRunError
from fmriflow.preproc.manifest import (
    PreprocConfig,
    PreprocManifest,
    PreprocStatus,
    RunQC,
    RunRecord,
    now_iso,
)

logger = logging.getLogger(__name__)

_ENTITY_RE = re.compile(r"([\w]+)-([\w]+)")


def _parse_bids_entities(filename: str) -> dict[str, str]:
    """Extract BIDS key-value entities from a filename."""
    return dict(_ENTITY_RE.findall(Path(filename).stem))


def _parse_params(config: PreprocConfig) -> FmriprepParams:
    """Build FmriprepParams from a PreprocConfig's backend_params."""
    return FmriprepParams.from_dict(config.backend_params)


@register_backend("fmriprep")
class FmriprepBackend:
    """Wraps fmriprep for preprocessing fMRI data.

    Supports bare install, Singularity, and Docker invocations.
    The ``collect()`` method can build a manifest from existing fmriprep
    derivative outputs without re-running.
    """

    name = "fmriprep"

    def validate(self, config: PreprocConfig) -> list[str]:
        params = _parse_params(config)
        errors = params.validate()

        if not self._find_fmriprep(params):
            errors.append(
                "fmriprep not found. Install via pip, or set "
                "container to a Singularity/Docker image."
            )

        if not config.bids_dir or not Path(config.bids_dir).is_dir():
            errors.append(f"BIDS directory not found: {config.bids_dir}")

        return errors

    def run(self, config: PreprocConfig) -> PreprocManifest:
        params = _parse_params(config)
        cmd = self._build_command(config, params)
        logger.info("Running fmriprep: %s", " ".join(cmd))

        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )

        tail: list[str] = []
        for line in proc.stdout:
            stripped = line.rstrip()
            logger.info("[fmriprep] %s", stripped)
            tail.append(stripped)
            if len(tail) > 50:
                tail.pop(0)
        proc.wait()

        if proc.returncode != 0:
            last_output = "\n".join(tail[-20:])
            raise BackendRunError(
                f"fmriprep exited with code {proc.returncode}\n"
                f"Last output:\n{last_output}",
                backend="fmriprep",
                subject=config.subject,
                returncode=proc.returncode,
                stderr=last_output,
            )

        return self.collect(config)

    def status(self, config: PreprocConfig) -> PreprocStatus:
        output_dir = Path(config.output_dir)
        sub_dir = output_dir / f"sub-{config.subject}"

        if not sub_dir.exists():
            return PreprocStatus(status="pending")

        # Check for html report — fmriprep writes this at the end
        reports = list(output_dir.glob(f"sub-{config.subject}*.html"))
        if reports:
            return PreprocStatus(status="completed")

        return PreprocStatus(status="running", detail="Output directory exists but no report found")

    def collect(self, config: PreprocConfig) -> PreprocManifest:
        """Build manifest from existing fmriprep derivative outputs."""
        params = _parse_params(config)
        output_dir = Path(config.output_dir)
        sub_dir = output_dir / f"sub-{config.subject}"

        if not sub_dir.exists():
            # Try without the sub- prefix (some layouts)
            sub_dir = output_dir
            if not sub_dir.exists():
                raise FileNotFoundError(
                    f"fmriprep output directory not found: "
                    f"{output_dir / f'sub-{config.subject}'}"
                )

        runs = []
        space = params.output_spaces[0] if params.output_spaces else "T1w"
        # Strip resolution/density suffixes for matching (e.g. "MNI152NLin2009cAsym:res-2" → "MNI152NLin2009cAsym")
        space_base = space.split(":")[0]

        # Find all preprocessed BOLD files
        for nii in sorted(sub_dir.rglob("*_desc-preproc_bold.nii.gz")):
            entities = _parse_bids_entities(nii.name)

            # Filter by space if specified
            nii_space = entities.get("space", "")
            if nii_space and nii_space != space_base:
                continue

            # Resolve run name
            run_name = self._resolve_run_name(entities, config.run_map)

            # Find corresponding confounds file
            confounds_file = self._find_confounds(nii)

            # Get shape and n_trs
            shape, n_trs = self._get_nifti_info(nii)

            # Extract QC from confounds
            qc = self._extract_qc(confounds_file) if confounds_file else None

            runs.append(RunRecord(
                run_name=run_name,
                source_file=self._infer_source(nii, entities, config),
                output_file=str(nii.relative_to(output_dir)),
                n_trs=n_trs,
                n_voxels=None,
                shape=shape,
                confounds_file=(
                    str(confounds_file.relative_to(output_dir))
                    if confounds_file else None
                ),
                qc=qc,
            ))

        return PreprocManifest(
            subject=config.subject,
            dataset=config.task or "unknown",
            sessions=config.sessions or [],
            runs=runs,
            backend="fmriprep",
            backend_version=self._get_version(params),
            parameters=params.to_dict(),
            space=space_base,
            resolution=self._resolve_resolution(space),
            confounds_applied=[],
            additional_steps=self._resolve_steps(params),
            output_dir=str(output_dir),
            output_format="cifti" if params.cifti_output else "nifti",
            file_pattern=(
                "sub-{subject}_ses-{session}_task-{task}_run-{run}"
                f"_space-{space_base}_desc-preproc_bold.nii.gz"
            ),
            created=now_iso(),
            pipeline_version=None,
            checksum=None,
        )

    # ── Private helpers ──────────────────────────────────────────

    def _find_fmriprep(self, params: FmriprepParams) -> bool:
        """Check if fmriprep is available."""
        if params.container:
            return Path(params.container).exists()
        return shutil.which("fmriprep") is not None

    def _build_command(
        self,
        config: PreprocConfig,
        params: FmriprepParams,
    ) -> list[str]:
        """Build the fmriprep CLI command."""
        # Base command: container or bare
        if params.container:
            cmd = self._build_container_prefix(config, params)
        else:
            cmd = [
                "fmriprep",
                config.bids_dir, config.output_dir,
                "participant",
                "--participant-label", config.subject,
            ]
            if config.work_dir:
                cmd += ["-w", config.work_dir]

        # All structured flags
        cmd += params.to_command_args()

        return cmd

    def _build_container_prefix(
        self,
        config: PreprocConfig,
        params: FmriprepParams,
    ) -> list[str]:
        """Build the container invocation prefix."""
        if params.container_type == "singularity":
            cmd = [
                "singularity", "run", "--cleanenv",
                "-B", f"{config.bids_dir}:/data:ro",
                "-B", f"{config.output_dir}:/out",
            ]
            if config.work_dir:
                cmd += ["-B", f"{config.work_dir}:/work"]
            cmd += [
                params.container,
                "/data", "/out", "participant",
                "--participant-label", config.subject,
            ]
            if config.work_dir:
                cmd += ["-w", "/work"]
        elif params.container_type == "docker":
            cmd = [
                "docker", "run", "--rm",
                "-v", f"{config.bids_dir}:/data:ro",
                "-v", f"{config.output_dir}:/out",
            ]
            if config.work_dir:
                cmd += ["-v", f"{config.work_dir}:/work"]
            cmd += [
                params.container,
                "/data", "/out", "participant",
                "--participant-label", config.subject,
            ]
            if config.work_dir:
                cmd += ["-w", "/work"]
        else:
            raise ValueError(f"Unknown container_type: {params.container_type}")

        return cmd

    def _resolve_run_name(
        self,
        entities: dict[str, str],
        run_map: dict[str, str] | None,
    ) -> str:
        """Derive a pipeline run name from BIDS entities."""
        parts = []
        if "ses" in entities:
            parts.append(f"ses-{entities['ses']}")
        if "run" in entities:
            parts.append(f"run-{entities['run']}")
        key = "_".join(parts) if parts else entities.get("run", "unknown")

        if run_map and key in run_map:
            return run_map[key]
        return key

    def _find_confounds(self, bold_path: Path) -> Path | None:
        """Find the confounds TSV matching a preprocessed BOLD file."""
        confounds_name = bold_path.name.replace(
            "_desc-preproc_bold.nii.gz",
            "_desc-confounds_timeseries.tsv",
        )
        confounds_path = bold_path.parent / confounds_name
        return confounds_path if confounds_path.exists() else None

    def _get_nifti_info(self, path: Path) -> tuple[list[int], int]:
        """Get shape and n_trs from a NIfTI file."""
        try:
            import nibabel as nib
            img = nib.load(path)
            shape = list(img.shape)
            n_trs = shape[-1] if len(shape) == 4 else shape[0]
            return shape, n_trs
        except Exception:
            logger.warning("Could not read NIfTI info from %s", path)
            return [], 0

    def _extract_qc(self, confounds_path: Path | None) -> RunQC | None:
        """Extract QC metrics from a confounds TSV."""
        if confounds_path is None:
            return None
        try:
            import pandas as pd
            df = pd.read_csv(confounds_path, sep="\t")
            fd = df.get("framewise_displacement")
            if fd is not None:
                fd_vals = fd.dropna()
                return RunQC(
                    mean_fd=float(fd_vals.mean()) if len(fd_vals) > 0 else None,
                    max_fd=float(fd_vals.max()) if len(fd_vals) > 0 else None,
                    n_high_motion_trs=int((fd_vals > 0.5).sum()),
                    tsnr_median=None,
                    n_outlier_trs=None,
                )
        except Exception:
            logger.warning("Could not extract QC from %s", confounds_path)
        return None

    def _infer_source(
        self,
        output_path: Path,
        entities: dict[str, str],
        config: PreprocConfig,
    ) -> str:
        """Infer the source BOLD path from entities."""
        parts = [f"sub-{config.subject}"]
        if "ses" in entities:
            parts.append(f"ses-{entities['ses']}")
        parts.append("func")

        name_parts = [f"sub-{config.subject}"]
        if "ses" in entities:
            name_parts.append(f"ses-{entities['ses']}")
        if config.task:
            name_parts.append(f"task-{config.task}")
        if "run" in entities:
            name_parts.append(f"run-{entities['run']}")
        name_parts.append("bold.nii.gz")

        return str(Path(*parts) / "_".join(name_parts))

    def _get_version(self, params: FmriprepParams) -> str:
        """Get the fmriprep version."""
        try:
            result = subprocess.run(
                ["fmriprep", "--version"],
                capture_output=True, text=True, timeout=10,
            )
            return result.stdout.strip()
        except Exception:
            return "unknown"

    def _resolve_resolution(self, space: str) -> str:
        """Extract resolution from a space string like 'MNI152NLin2009cAsym:res-2'."""
        if ":" in space:
            for part in space.split(":")[1:]:
                if part.startswith("res-"):
                    return part.replace("res-", "") + "mm"
                if part.startswith("den-"):
                    return part
        return "native"

    def _resolve_steps(self, params: FmriprepParams) -> list[str]:
        """Build the additional_steps list from params."""
        steps = []
        if params.use_aroma:
            steps.append("ica_aroma")
        if params.use_syn_sdc:
            steps.append("syn_sdc")
        return steps
