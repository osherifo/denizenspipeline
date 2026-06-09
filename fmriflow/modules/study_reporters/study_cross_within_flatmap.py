"""StudyCrossWithinFlatmap — RGB flatmap encoding within vs cross accuracy.

Reads the ``(n_vertices, 2)`` array from ``cross_within_summary``
(column 0 = within-modality max accuracy, column 1 = cross-modality
mean accuracy) and renders a single flatmap whose RGB colour per
vertex encodes both axes:

* red channel ∝ within-modality max
* green channel ∝ cross-modality mean
* blue channel = green

So:

* well predicted both within AND across → white-ish
* well predicted within only → orange
* well predicted across only → cyan (rare)
* poorly predicted either way → dark

Saturation is clipped to [vmin, vmax] separately per channel.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from fmriflow.core.study_types import StudyResult
from fmriflow.modules._decorators import study_reporter
from fmriflow.modules.study_analyzers._helpers import my_cfg

logger = logging.getLogger(__name__)


@study_reporter("study_cross_within_flatmap")
class StudyCrossWithinFlatmapReporter:
    """RGB summary flatmap pairing within- and cross-modality accuracy."""

    name = "study_cross_within_flatmap"
    PARAM_SCHEMA = {
        "input_key": {
            "type": "str",
            "default": "study.cross_within_summary",
            "description": (
                "Study-artifact key for the (n_vertices, 2) array."
            ),
        },
        "within_range": {
            "type": "list[float]",
            "default": [0.0, 0.3],
            "description": "Clip range for the within-modality channel.",
        },
        "cross_range": {
            "type": "list[float]",
            "default": [0.0, 0.3],
            "description": "Clip range for the cross-modality channel.",
        },
        "with_curvature": {"type": "bool", "default": True},
        "dpi": {"type": "int", "default": 100, "min": 50},
        "filename": {
            "type": "str",
            "default": "fig9_cross_vs_within.png",
            "description": "Output PNG filename.",
        },
    }

    def report(self, study: StudyResult, config: dict) -> dict[str, str]:
        cfg = my_cfg(config, self.name)
        input_key = cfg.get("input_key", "study.cross_within_summary")
        if not study.has(input_key):
            logger.warning(
                "study_cross_within_flatmap: '%s' missing from study "
                "artifacts — did cross_within_summary run?", input_key)
            return {}

        arr = np.asarray(study.get(input_key)).astype(np.float32)
        if arr.ndim != 2 or arr.shape[1] != 2:
            logger.warning(
                "study_cross_within_flatmap: expected (n_verts, 2) array, "
                "got shape %s", arr.shape)
            return {}

        try:
            import cortex
        except ImportError as exc:
            logger.warning(
                "study_cross_within_flatmap: pycortex not importable (%s)", exc)
            return {}

        wmin, wmax = cfg.get("within_range", [0.0, 0.3])
        cmin, cmax = cfg.get("cross_range", [0.0, 0.3])

        within = np.clip((arr[:, 0] - wmin) / max(wmax - wmin, 1e-9), 0, 1)
        cross = np.clip((arr[:, 1] - cmin) / max(cmax - cmin, 1e-9), 0, 1)

        # Encode the pair as a Vertex2D-style RGB triple so a single
        # pycortex call lands the joint map on the surface.
        red = within
        green = cross
        blue = cross

        outdir_str = cfg.get("output_dir") or config.get("output_dir")
        outdir = Path(outdir_str).resolve() if outdir_str else Path.cwd()
        outdir.mkdir(parents=True, exist_ok=True)
        path = outdir / cfg.get("filename", "fig9_cross_vs_within.png")

        try:
            verts = cortex.VertexRGB(
                (red * 255).astype(np.uint8),
                (green * 255).astype(np.uint8),
                (blue * 255).astype(np.uint8),
                "fsaverage",
            )
        except Exception as exc:
            logger.warning(
                "study_cross_within_flatmap: cortex.VertexRGB failed: %s", exc)
            return {}

        try:
            cortex.quickflat.make_png(
                str(path), verts,
                with_curvature=cfg.get("with_curvature", True),
                dpi=cfg.get("dpi", 100),
            )
        except Exception as exc:
            logger.warning(
                "study_cross_within_flatmap: quickflat.make_png failed: %s",
                exc)
            return {}
        return {"study_cross_within_flatmap": str(path)}

    def validate_config(self, config: dict) -> list[str]:
        return []
