"""R2FlatmapReporter — coefficient-of-determination flatmap.

Reads ``result.metadata.scores_r2`` (written by the
multiple_kernel_ridge model) and renders a diverging colormap because
R² can go negative (predictions worse than the per-voxel mean).

The vmin/vmax defaults are symmetric so the midpoint of the cmap is
exactly r² = 0 — easy to read at a glance.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from fmriflow.core.types import ModelResult
from fmriflow.modules._decorators import reporter
from fmriflow.modules.reporters.r_flatmap import _render

logger = logging.getLogger(__name__)


@reporter("r2_flatmap")
class R2FlatmapReporter:
    """Render the per-voxel R² as a pycortex flatmap with a diverging cmap."""

    name = "r2_flatmap"
    PARAM_SCHEMA = {
        "cmap": {"type": "string", "default": "RdBu_r"},
        "vmin": {"type": "float", "default": -0.1},
        "vmax": {"type": "float", "default": 0.1},
        "threshold": {"type": "float", "description": "Mask |r²| below this to NaN"},
        "with_curvature": {"type": "bool", "default": True},
        "dpi": {"type": "int", "default": 100, "min": 50},
        "filename": {"type": "str", "default": "r2_flatmap.png"},
    }

    def report(self, result: ModelResult, context, config: dict) -> dict[str, str]:
        opts = config.get("reporting", {}).get("r2_flatmap", {})
        scores = (result.metadata or {}).get("scores_r2")
        if scores is None:
            logger.warning(
                "r2_flatmap: scores_r2 not in metadata — model didn't emit it. "
                "Skipping.")
            return {}
        return _render(
            scores=np.asarray(scores),
            ctx=context,
            output_dir=Path(config.get("reporting", {}).get("output_dir", "./results")),
            cmap=opts.get("cmap", "RdBu_r"),
            vmin=opts.get("vmin", -0.1),
            vmax=opts.get("vmax", 0.1),
            threshold=opts.get("threshold"),
            with_curvature=opts.get("with_curvature", True),
            dpi=opts.get("dpi", 100),
            filename=opts.get("filename", "r2_flatmap.png"),
            return_key="r2_flatmap",
        )

    def validate_config(self, config: dict) -> list[str]:
        return []
