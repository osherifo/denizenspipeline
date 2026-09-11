"""PearsonRFlatmapReporter — Pearson r prediction-accuracy flatmap.

Reads ``result.metadata.scores_pearson_r`` (written by the
multiple_kernel_ridge model) and renders a pycortex flatmap on the
subject's native surface. Falls back to ``result.scores`` if the
metric-specific key isn't present.

Sensible defaults for an in-bounds (-1, 1) metric:
- ``cmap`` = ``magma`` (sequential, since we typically thresh ≥ 0)
- ``vmin / vmax`` = 0 / 0.3
- ``threshold`` = 0.05 (mask noise to NaN; pycortex paints those grey)

When ``significance_key`` is set, a second PNG is emitted alongside
the unmasked one with non-significant voxels rendered as NaN. The
significance dict is expected to carry a boolean ``sig_mask`` of
length n_voxels (e.g. what the ``block_permutation_significance``
analyzer publishes under ``analysis.significance``).
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from fmriflow.core.mask_utils import has_real_mask, unmask_scores
from fmriflow.core.types import ModelResult, ResponseData
from fmriflow.modules._decorators import reporter
from fmriflow.modules.reporters._quickflat import quickflat_png

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
        "significance_key": {
            "type": "str",
            "default": None,
            "description": (
                "Optional context key holding a significance dict with a "
                "boolean ``sig_mask`` (length = n_voxels). When set, the "
                "reporter emits a second PNG with non-significant voxels "
                "masked to NaN (grey cortex), alongside the unmasked one. "
                "Wire this to the output_key of e.g. "
                "block_permutation_significance."
            ),
        },
        "fdr_filename": {
            "type": "str",
            "default": None,
            "description": (
                "Filename for the FDR-masked render. Defaults to "
                "``<stem>_fdr<ext>`` derived from ``filename``."
            ),
        },
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
        scores = np.asarray(scores).astype(np.float32).copy()

        output_dir = Path(config.get("reporting", {}).get("output_dir", "./results"))
        render_kwargs = dict(
            ctx=context, output_dir=output_dir,
            cmap=opts.get("cmap", "magma"),
            vmin=opts.get("vmin", 0.0),
            vmax=opts.get("vmax", 0.3),
            threshold=opts.get("threshold"),
            with_curvature=opts.get("with_curvature", True),
            dpi=opts.get("dpi", 100),
        )
        base_filename = opts.get("filename", "r_flatmap.png")
        outputs: dict[str, str] = {}
        outputs.update(_render(
            scores=scores, filename=base_filename,
            return_key="r_flatmap", **render_kwargs))

        sig_key = opts.get("significance_key")
        if sig_key:
            sig = _resolve_significance(context, sig_key)
            if sig is None:
                logger.warning(
                    "r_flatmap: significance_key=%r not in context — "
                    "skipping fdr-masked render", sig_key)
            elif sig.shape != scores.shape:
                logger.warning(
                    "r_flatmap: sig_mask shape %s != scores shape %s — "
                    "skipping fdr-masked render", sig.shape, scores.shape)
            else:
                masked = scores.copy()
                masked[~sig] = np.nan
                fdr_filename = opts.get(
                    "fdr_filename", _insert_suffix(base_filename, "_fdr"))
                outputs.update(_render(
                    scores=masked, filename=fdr_filename,
                    return_key="r_flatmap_fdr", **render_kwargs))
        return outputs

    def validate_config(self, config: dict) -> list[str]:
        return []


def _insert_suffix(filename: str, suffix: str) -> str:
    """Insert ``suffix`` before the extension, preserving any parent dirs."""
    p = Path(filename)
    return str(p.with_name(f"{p.stem}{suffix}{p.suffix}"))


def _resolve_significance(ctx, key: str):
    """Pull the sig_mask out of a context-key holding a significance dict."""
    if not ctx.has(key):
        return None
    obj = ctx.get(key)
    if isinstance(obj, dict):
        mask = obj.get("sig_mask")
    else:
        mask = getattr(obj, "sig_mask", None)
    if mask is None:
        return None
    return np.asarray(mask).astype(bool)


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
        quickflat_png(
            str(path), vol,
            with_curvature=with_curvature, dpi=dpi,
        )
    except Exception as exc:
        logger.warning("%s: quickflat.make_png failed: %s", return_key, exc)
        return {}
    return {return_key: str(path)}
