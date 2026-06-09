"""PearsonRFlatmapReporter — Pearson r prediction-accuracy flatmap.

Reads ``result.metadata.scores_pearson_r`` (written by the
multiple_kernel_ridge model) and renders a pycortex flatmap on the
subject's native surface. Falls back to ``result.scores`` if the
metric-specific key isn't present.

Sensible defaults for an in-bounds (-1, 1) metric:
- ``cmap`` = ``magma`` (sequential, since we typically thresh ≥ 0)
- ``vmin / vmax`` = 0 / 0.3
- ``threshold`` = 0.05 (mask noise to NaN; pycortex paints those grey)
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from fmriflow.core.mask_utils import has_real_mask, unmask_scores
from fmriflow.core.types import ModelResult, ResponseData
from fmriflow.modules._decorators import reporter

logger = logging.getLogger(__name__)


@reporter("r_flatmap")
class PearsonRFlatmapReporter:
    """Render the per-voxel Pearson r as a pycortex flatmap."""

    name = "r_flatmap"
    PARAM_SCHEMA = {
        "cmap": {"type": "string", "default": "magma"},
        "vmin": {"type": "float", "default": 0.0},
        "vmax": {"type": "float", "default": 0.3},
        "threshold": {"type": "float", "default": None},
        "with_curvature": {"type": "bool", "default": True},
        "dpi": {"type": "int", "default": 100, "min": 50},
        "filename": {"type": "str", "default": "r_flatmap.png"},
    }

    def report(self, result: ModelResult, context, config: dict) -> dict[str, str]:
        opts = config.get("reporting", {}).get("r_flatmap", {})
        scores = (result.metadata or {}).get("scores_pearson_r")
        if scores is None:
            logger.info("r_flatmap: scores_pearson_r not in metadata; "
                        "falling back to result.scores")
            scores = result.scores
        return _render(
            scores=np.asarray(scores),
            ctx=context,
            output_dir=Path(config.get("reporting", {}).get("output_dir", "./results")),
            cmap=opts.get("cmap", "magma"),
            vmin=opts.get("vmin", 0.0),
            vmax=opts.get("vmax", 0.3),
            threshold=opts.get("threshold"),
            with_curvature=opts.get("with_curvature", True),
            dpi=opts.get("dpi", 100),
            filename=opts.get("filename", "r_flatmap.png"),
            return_key="r_flatmap",
        )

    def validate_config(self, config: dict) -> list[str]:
        return []


def _render(*, scores: np.ndarray, ctx, output_dir: Path,
            cmap: str, vmin: float, vmax: float, threshold: float | None,
            with_curvature: bool, dpi: int, filename: str,
            return_key: str) -> dict[str, str]:
    try:
        import cortex
    except ImportError as exc:
        logger.warning("%s: pycortex not importable: %s", return_key, exc)
        return {}

    resp_data = ctx.get("responses", ResponseData)
    output_dir.mkdir(parents=True, exist_ok=True)

    s = scores.copy().astype(np.float32)
    if threshold is not None:
        s[s < threshold] = np.nan
    if has_real_mask(resp_data.mask):
        s = unmask_scores(s, resp_data.mask)

    try:
        vol = cortex.Volume(
            s, resp_data.surface, resp_data.transform,
            vmin=vmin, vmax=vmax, cmap=cmap,
        )
    except ValueError as exc:
        if "mask" in str(exc).lower():
            logger.warning(
                "%s: pycortex mask/voxel mismatch — skipping (see error KB 0035).",
                return_key)
            return {}
        raise

    path = output_dir / filename
    try:
        cortex.quickflat.make_png(
            str(path), vol,
            with_curvature=with_curvature, dpi=dpi,
        )
    except Exception as exc:
        logger.warning("%s: quickflat.make_png failed: %s", return_key, exc)
        return {}
    return {return_key: str(path)}
