"""Custom shell command backend — runs an arbitrary preprocessing script."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from denizenspipeline.preproc.backends import register_backend
from denizenspipeline.preproc.errors import BackendRunError
from denizenspipeline.preproc.manifest import (
    PreprocConfig,
    PreprocManifest,
    PreprocStatus,
    RunRecord,
    now_iso,
)

logger = logging.getLogger(__name__)


@register_backend("custom")
class CustomBackend:
    """Run a custom preprocessing command.

    The command is a template with ``{subject}``, ``{session}``,
    ``{input_dir}``, ``{output_dir}`` placeholders.  The backend runs it,
    then scans the output directory for result files matching a configurable
    pattern.

    backend_params:
        command : str — shell command template (required)
        file_pattern : str — glob pattern for output files (default: ``*.nii.gz``)
        version : str — version string for the manifest (default: ``unknown``)
        space : str — output space label (default: ``native``)
        output_format : str — output format (default: ``nifti``)
    """

    name = "custom"

    def validate(self, config: PreprocConfig) -> list[str]:
        errors = []
        if "command" not in config.backend_params:
            errors.append(
                "custom backend requires backend_params.command "
                "(shell command template)"
            )
        input_dir = config.raw_dir or config.bids_dir
        if not input_dir:
            errors.append(
                "custom backend requires raw_dir or bids_dir as input"
            )
        elif not Path(input_dir).is_dir():
            errors.append(f"Input directory not found: {input_dir}")
        return errors

    def run(self, config: PreprocConfig) -> PreprocManifest:
        cmd_template = config.backend_params["command"]
        input_dir = config.raw_dir or config.bids_dir or ""

        cmd = cmd_template.format(
            subject=config.subject,
            session=config.sessions[0] if config.sessions else "",
            input_dir=input_dir,
            output_dir=config.output_dir,
        )

        logger.info("Running custom preprocessing: %s", cmd)

        # Ensure output dir exists
        Path(config.output_dir).mkdir(parents=True, exist_ok=True)

        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
        )

        if result.stdout:
            for line in result.stdout.strip().splitlines():
                logger.info("[custom] %s", line)

        if result.returncode != 0:
            raise BackendRunError(
                f"Custom command failed (exit {result.returncode}): "
                f"{result.stderr[:500]}",
                backend="custom",
                subject=config.subject,
                returncode=result.returncode,
                stderr=result.stderr,
            )

        return self.collect(config)

    def status(self, config: PreprocConfig) -> PreprocStatus:
        output_dir = Path(config.output_dir)
        if not output_dir.exists():
            return PreprocStatus(status="pending")

        file_pattern = config.backend_params.get("file_pattern", "*.nii.gz")
        outputs = list(output_dir.rglob(file_pattern))
        if outputs:
            return PreprocStatus(
                status="completed",
                detail=f"{len(outputs)} output files found",
            )
        return PreprocStatus(status="running")

    def collect(self, config: PreprocConfig) -> PreprocManifest:
        """Build manifest by scanning the output directory."""
        output_dir = Path(config.output_dir)
        file_pattern = config.backend_params.get("file_pattern", "*.nii.gz")

        runs = []
        for f in sorted(output_dir.rglob(file_pattern)):
            run_name = f.stem.split("_")[0]
            if config.run_map:
                run_name = config.run_map.get(run_name, run_name)

            shape, n_trs = _get_file_info(f)

            runs.append(RunRecord(
                run_name=run_name,
                source_file="",
                output_file=str(f.relative_to(output_dir)),
                n_trs=n_trs,
                n_voxels=None,
                shape=shape,
                confounds_file=None,
                qc=None,
            ))

        space = config.backend_params.get("space", "native")
        output_format = config.backend_params.get("output_format", "nifti")

        return PreprocManifest(
            subject=config.subject,
            dataset=config.task or "unknown",
            sessions=config.sessions or [],
            runs=runs,
            backend="custom",
            backend_version=config.backend_params.get("version", "unknown"),
            parameters=config.backend_params,
            space=space,
            resolution=config.backend_params.get("resolution", "native"),
            confounds_applied=[],
            additional_steps=config.backend_params.get("steps", []),
            output_dir=str(output_dir),
            output_format=output_format,
            file_pattern=file_pattern,
            created=now_iso(),
            pipeline_version=None,
            checksum=None,
        )


def _get_file_info(path: Path) -> tuple[list[int], int]:
    """Best-effort shape/n_trs extraction."""
    suffix = "".join(path.suffixes)
    if ".nii" in suffix:
        try:
            import nibabel as nib
            img = nib.load(path)
            shape = list(img.shape)
            n_trs = shape[-1] if len(shape) == 4 else shape[0]
            return shape, n_trs
        except Exception:
            pass
    return [], 0
