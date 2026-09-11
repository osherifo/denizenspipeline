"""FsaverageFlatmapReporter — renders fsaverage-projected scores on the fsaverage cortical surface.

Reads ``analysis.fsaverage_scores`` (produced by the ``project_to_fsaverage``
analyzer). Renders a pycortex flatmap with ``subject='fsaverage'`` so every
subject lands on the same cortical surface — directly usable for cross-subject
comparisons (and the input to the group ``voxelwise_mean`` analyzer that
produces the mean-accuracy group flatmap).

If the fsaverage projection wasn't produced (no analyzer in the pipeline, or
the analyzer hit FreeSurfer / mask-mismatch issues), this reporter no-ops with
a warning so the rest of the report stage continues.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np

from fmriflow.core.types import ModelResult
from fmriflow.modules._decorators import reporter

logger = logging.getLogger(__name__)


@reporter("fsaverage_flatmap")
class FsaverageFlatmapReporter:
    """Render an fsaverage-space score map as a quickflat PNG."""

    name = "fsaverage_flatmap"
    PARAM_SCHEMA = {
        "input_key": {
            "type": "str",
            "default": "analysis.fsaverage_scores",
            "description": "Subject-context key holding the fsaverage array.",
        },
        "cmap": {"type": "string", "default": "inferno", "description": "Matplotlib colormap"},
        "vmin": {"type": "float", "default": 0.0},
        "vmax": {"type": "float", "default": 0.5},
        "with_curvature": {"type": "bool", "default": True},
        "threshold": {"type": "float", "description": "Mask scores below this to NaN"},
        "dpi": {"type": "int", "default": 100, "min": 50},
        "filename": {"type": "str", "default": "fsaverage_flatmap.png"},
    }

    def report(self, result: ModelResult, context, config: dict) -> dict[str, str]:
        opts = config.get("reporting", {}).get("fsaverage_flatmap", {})
        input_key = opts.get("input_key", "analysis.fsaverage_scores")

        data = _resolve_key(context, input_key)
        if data is None:
            logger.warning(
                "fsaverage_flatmap: '%s' not in context — skipping. "
                "Add 'project_to_fsaverage' to the analyze stage and check "
                "its log line for the underlying error.", input_key)
            return {}

        return _render_fsaverage_png(
            data=np.asarray(data).astype(np.float32),
            output_dir=Path(config.get("reporting", {})
                            .get("output_dir", "./results")),
            filename=opts.get("filename", "fsaverage_flatmap.png"),
            cmap=opts.get("cmap", "inferno"),
            vmin=opts.get("vmin", 0.0),
            vmax=opts.get("vmax", 0.5),
            with_curvature=opts.get("with_curvature", True),
            threshold=opts.get("threshold"),
            dpi=opts.get("dpi", 100),
            return_key="fsaverage_flatmap",
        )

    def validate_config(self, config: dict) -> list[str]:
        return []


# ─── shared helpers ────────────────────────────────────────────


from fmriflow.core.context_keys import resolve_context_key as _resolve_key  # noqa: E402


def _render_fsaverage_png(*, data: np.ndarray, output_dir: Path, filename: str,
                          cmap: str, vmin: float, vmax: float,
                          with_curvature: bool, threshold: float | None,
                          dpi: int, return_key: str) -> dict[str, str]:
    try:
        import cortex
    except ImportError as exc:
        logger.warning("fsaverage_flatmap: pycortex not importable: %s", exc)
        return {}

    output_dir.mkdir(parents=True, exist_ok=True)
    arr = data.copy()
    if threshold is not None:
        arr[arr < threshold] = np.nan

    try:
        vert = cortex.Vertex(arr, "fsaverage", vmin=vmin, vmax=vmax, cmap=cmap)
    except Exception as exc:
        logger.warning("fsaverage_flatmap: cortex.Vertex failed: %s", exc)
        return {}

    path = output_dir / filename
    try:
        cortex.quickflat.make_png(
            str(path), vert,
            with_curvature=with_curvature,
            dpi=dpi,
        )
    except Exception as exc:
        logger.warning(
            "fsaverage_flatmap: quickflat.make_png failed: %s", exc)
        return {}
    return {return_key: str(path)}
