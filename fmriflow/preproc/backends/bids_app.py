"""Generic BIDS-App backend — wraps any BIDS-App (fmriprep, mriqc, etc.)
using the standard ``<app> <bids_dir> <output_dir> participant`` convention."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from fmriflow.preproc.backends import register_backend
from fmriflow.preproc.errors import BackendRunError
from fmriflow.preproc.manifest import (
    PreprocConfig,
    PreprocManifest,
    PreprocStatus,
    RunRecord,
    now_iso,
)

logger = logging.getLogger(__name__)


@register_backend("bids_app")
class BidsAppBackend:
    """Generic wrapper for any BIDS-App.

    backend_params:
        container : str — Docker/Singularity image, or bare command (required)
        container_type : str — "docker", "singularity", or "bare" (default: "singularity")
        extra_args : list[str] — additional CLI arguments
        file_pattern : str — glob for output files (default: "*_desc-preproc_bold.nii.gz")
        space : str — output space label (default: "native")
    """

    name = "bids_app"

    def validate(self, config: PreprocConfig) -> list[str]:
        errors = []
        if "container" not in config.backend_params:
            errors.append(
                "bids_app backend requires backend_params.container "
                "(Docker/Singularity image or bare command path)"
            )
        if not config.bids_dir or not Path(config.bids_dir).is_dir():
            errors.append(f"BIDS directory not found: {config.bids_dir}")
        return errors

    def run(self, config: PreprocConfig) -> PreprocManifest:
        cmd = self._build_command(config)
        logger.info("Running BIDS-App: %s", " ".join(cmd))

        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )

        for line in proc.stdout:
            logger.info("[bids_app] %s", line.rstrip())
        proc.wait()

        if proc.returncode != 0:
            raise BackendRunError(
                f"BIDS-App exited with code {proc.returncode}",
                backend="bids_app",
                subject=config.subject,
                returncode=proc.returncode,
                stderr="",
            )

        return self.collect(config)

    def status(self, config: PreprocConfig) -> PreprocStatus:
        output_dir = Path(config.output_dir)
        if not output_dir.exists():
            return PreprocStatus(status="pending")

        pattern = config.backend_params.get(
            "file_pattern", "*_desc-preproc_bold.nii.gz"
        )
        outputs = list(output_dir.rglob(pattern))
        if outputs:
            return PreprocStatus(
                status="completed",
                detail=f"{len(outputs)} output files found",
            )
        return PreprocStatus(status="running")

    def collect(self, config: PreprocConfig) -> PreprocManifest:
        """Build manifest by scanning BIDS-App outputs."""
        output_dir = Path(config.output_dir)
        pattern = config.backend_params.get(
            "file_pattern", "*_desc-preproc_bold.nii.gz"
        )

        runs = []
        for f in sorted(output_dir.rglob(pattern)):
            run_name = f.stem.split("_")[0]
            if config.run_map:
                run_name = config.run_map.get(run_name, run_name)

            shape, n_trs = _get_nifti_info(f)

            runs.append(RunRecord(
                run_name=run_name,
                source_file="",
                output_file=str(f.relative_to(output_dir)),
                n_trs=n_trs,
                n_voxels=None,
                shape=shape,
            ))

        space = config.backend_params.get("space", "native")
        return PreprocManifest(
            subject=config.subject,
            dataset=config.task or "unknown",
            sessions=config.sessions or [],
            runs=runs,
            backend="bids_app",
            backend_version=config.backend_params.get("version", "unknown"),
            parameters=config.backend_params,
            space=space,
            resolution=config.backend_params.get("resolution", "native"),
            confounds_applied=[],
            additional_steps=[],
            output_dir=str(output_dir),
            output_format="nifti",
            file_pattern=pattern,
            created=now_iso(),
            pipeline_version=None,
            checksum=None,
        )

    def _build_command(self, config: PreprocConfig) -> list[str]:
        container = config.backend_params["container"]
        container_type = config.backend_params.get("container_type", "singularity")

        if container_type == "singularity":
            cmd = [
                "singularity", "run", "--cleanenv",
                "-B", f"{config.bids_dir}:/data:ro",
                "-B", f"{config.output_dir}:/out",
            ]
            if config.work_dir:
                cmd += ["-B", f"{config.work_dir}:/work"]
            cmd += [
                container,
                "/data", "/out", "participant",
                "--participant-label", config.subject,
            ]
        elif container_type == "docker":
            cmd = [
                "docker", "run", "--rm",
                "-v", f"{config.bids_dir}:/data:ro",
                "-v", f"{config.output_dir}:/out",
            ]
            if config.work_dir:
                cmd += ["-v", f"{config.work_dir}:/work"]
            cmd += [
                container,
                "/data", "/out", "participant",
                "--participant-label", config.subject,
            ]
        else:
            # Bare install
            cmd = [
                container, config.bids_dir, config.output_dir,
                "participant", "--participant-label", config.subject,
            ]

        extra = config.backend_params.get("extra_args", [])
        if extra:
            cmd += extra

        return cmd


def _get_nifti_info(path: Path) -> tuple[list[int], int]:
    """Best-effort shape extraction."""
    try:
        import nibabel as nib
        img = nib.load(path)
        shape = list(img.shape)
        n_trs = shape[-1] if len(shape) == 4 else shape[0]
        return shape, n_trs
    except Exception:
        return [], 0
