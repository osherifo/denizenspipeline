"""Passthrough — use already-preprocessed data; emit manifest by scanning.

Stage-0 workflow that does **no preprocessing**. Scans
``config.derivatives_dir`` for files matching a configurable glob
(default ``*_desc-preproc_bold.nii.gz``), builds a ``RunRecord`` per
match, emits a ``PreprocManifest`` pointing at the existing files.

The intended use is "data was preprocessed externally (an older
fmriprep run, a custom pipeline, a collaborator's output); plug it
into the stack as-is and optionally add transforms (smooth, regress)
on top." No re-running of preproc.

Validation only catches *structural* problems (no ``derivatives_dir``
configured, the dir doesn't exist on disk, no subject id). The
scan itself runs in :meth:`to_manifest` — *no matching files* is
treated as a non-fatal warning and produces an empty-runs manifest
that downstream stages may reject. If you need stricter behaviour
(empty input → hard failure), wrap the workflow in a thin checker
or filter on ``len(manifest.runs)`` at the call site.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fmriflow.preproc.manifest import (
    PreprocManifest,
    RunRecord,
    now_iso,
)
from fmriflow.preproc.workflow_registry import register_preproc_workflow

logger = logging.getLogger(__name__)


@register_preproc_workflow("passthrough")
class PassthroughWorkflow:
    """Scan ``config.derivatives_dir`` for preprocessed files; no actual run."""

    name = "passthrough"
    version = "0.1.0"
    description = (
        "Use already-preprocessed data. Scans derivatives_dir for files "
        "matching the glob pattern and emits a manifest with one RunRecord "
        "per match. Adds zero preprocessing — useful when chaining transforms "
        "on top of externally-preprocessed data."
    )

    PARAM_SCHEMA: dict = {
        "space": {
            "type": "string",
            "default": "native",
            "description": "Output space label to record in the manifest.",
        },
        "file_pattern": {
            "type": "string",
            "default": "*_desc-preproc_bold.nii.gz",
            "description": "Glob pattern (rglob, anchored at derivatives_dir/sub-<subject>/) for preprocessed files.",
        },
        "output_format": {
            "type": "string",
            "default": "nifti",
            "enum": ["nifti", "cifti"],
            "description": "Output format label for the manifest.",
        },
    }

    REQUIRED_PYTHON: list[str] = []   # nibabel is optional — only used for shape extraction
    REQUIRED_TOOLS: list[str] = []
    REQUIRED_ENV: list[str] = []
    CONTAINER: str | None = None

    def validate(self, config: Any) -> list[str]:
        errors: list[str] = []
        deriv_raw = getattr(config, "derivatives_dir", None)
        if not deriv_raw:
            errors.append(
                "passthrough workflow requires StackRunConfig.derivatives_dir "
                "to point at a BIDS-derivatives directory."
            )
            return errors
        deriv = Path(deriv_raw)
        if not deriv.is_dir():
            errors.append(f"derivatives_dir does not exist: {deriv}")
            return errors

        subject = getattr(config, "subject", "")
        if not subject:
            errors.append("passthrough workflow requires a subject id.")
            return errors

        return errors

    def build(self, config: Any) -> Any:
        # No execution — manifest is built from the scan in to_manifest.
        return None

    def to_manifest(self, config: Any, wf_outputs: dict[str, Any]) -> PreprocManifest:
        deriv = Path(config.derivatives_dir)
        subject = config.subject
        params = dict(getattr(config, "backend_params", {}) or {})

        pattern = params.get("file_pattern", "*_desc-preproc_bold.nii.gz")
        space = params.get("space", "native")
        output_format = params.get("output_format", "nifti")

        sub_dir = deriv / f"sub-{subject}"
        scan_root = sub_dir if sub_dir.is_dir() else deriv

        matches = sorted(scan_root.rglob(pattern))
        runs: list[RunRecord] = []
        for f in matches:
            shape, n_trs = _file_shape(f)
            runs.append(
                RunRecord(
                    run_name=_run_name_from_filename(f),
                    source_file="",
                    output_file=str(f.relative_to(deriv)),
                    n_trs=n_trs,
                    shape=shape,
                    confounds_file=None,
                    qc=None,
                )
            )

        if not runs:
            logger.warning(
                "passthrough workflow found no files matching %r under %s — "
                "emitting empty-runs manifest. Downstream stages may reject this.",
                pattern, scan_root,
            )

        return PreprocManifest(
            subject=subject,
            dataset=getattr(config, "dataset", None) or "unknown",
            sessions=list(getattr(config, "sessions", []) or []),
            runs=runs,
            backend="passthrough",
            backend_version=self.version,
            parameters={
                "workflow": "passthrough",
                **params,
            },
            space=space,
            output_dir=str(deriv),
            output_format=output_format,
            file_pattern=pattern,
            additional_steps=[],
            created=now_iso(),
        )


def _file_shape(path: Path) -> tuple[list[int], int]:
    """Best-effort shape extraction. ``nibabel`` is optional — without it
    the manifest still records the file path, just with empty shape."""
    try:
        import nibabel as nib
    except ImportError:
        return [], 0
    try:
        img = nib.load(str(path))
        shape = list(img.shape)
        n_trs = shape[-1] if len(shape) == 4 else 1
        return shape, n_trs
    except Exception as e:
        logger.warning("Could not read shape from %s: %s", path, e)
        return [], 0


def _run_name_from_filename(path: Path) -> str:
    """Pull a BIDS-style run identifier from the filename.

    Looks for ``run-XX`` in the filename; falls back to the stem
    without extensions.
    """
    name = path.name
    for part in name.split("_"):
        if part.startswith("run-"):
            return part
    return path.stem.replace(".nii", "")
