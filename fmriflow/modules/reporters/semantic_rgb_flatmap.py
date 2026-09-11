"""SemanticRgbFlatmapReporter — render PC1/PC2/PC3 as an RGB flatmap.

Reads ``analysis.semantic_pc_projection`` (shape ``(n_components, n_voxels)``)
produced by the ``project_to_subspace`` subject-scope analyzer during the
GroupOrchestrator's second pass. Maps the first three PC channels to R/G/B
and renders a pycortex flatmap on the subject's native cortical surface.

This is the standard "semantic tuning map" view: voxels are coloured by
*where* in the shared semantic basis their tuning lands, not by prediction
accuracy.

Falls back to a no-op with a warning if:
- the PC projection isn't in context (no group second pass ran, or the
  ``project_to_subspace`` analyzer no-op'd because no group basis was bound);
- the pycortex mask voxel count doesn't match the response data (same
  flatmap-skip mechanic as the regular flatmap reporter, see error KB 0035).
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


@reporter("semantic_rgb_flatmap")
class SemanticRgbFlatmapReporter:
    """Render PC1/2/3 of an ``analysis.semantic_pc_projection`` as RGB flatmap."""

    name = "semantic_rgb_flatmap"
    PARAM_SCHEMA = {
        "input_key": {
            "type": "str",
            "default": "analysis.semantic_pc_projection",
            "description": "Subject-context key holding (K, n_voxels) PC projection.",
        },
        "channels": {
            "type": "list[int]",
            "default": [0, 1, 2],
            "description": "Which PC indices to map to R, G, B respectively.",
        },
        "with_curvature": {"type": "bool", "default": True},
        "dpi": {"type": "int", "default": 100, "min": 50},
        "min_voxel_significance": {
            "type": "float",
            "description": (
                "If set, voxels with result.scores below this are rendered as "
                "transparent (so non-significant voxels read as gray cortex)."
            ),
        },
        "filename": {"type": "str", "default": "semantic_rgb_flatmap.png"},
    }

    def report(self, result: ModelResult, context, config: dict) -> dict[str, str]:
        opts = config.get("reporting", {}).get("semantic_rgb_flatmap", {})
        input_key = opts.get("input_key", "analysis.semantic_pc_projection")
        channels = opts.get("channels", [0, 1, 2])
        if len(channels) != 3:
            logger.warning(
                "semantic_rgb_flatmap: 'channels' must have 3 elements, got %s",
                channels)
            return {}

        projection = _resolve_key(context, input_key)
        if projection is None:
            logger.warning(
                "semantic_rgb_flatmap: '%s' not in context — skipping. "
                "This reporter only produces output during the group "
                "orchestrator's second pass after stacked_weights_pca runs.",
                input_key)
            return {}
        projection = np.asarray(projection)
        if projection.ndim != 2 or projection.shape[0] < max(channels) + 1:
            logger.warning(
                "semantic_rgb_flatmap: projection has shape %s; need at least "
                "%d components for channels %s", projection.shape,
                max(channels) + 1, channels)
            return {}

        try:
            import cortex
        except ImportError as exc:
            logger.warning("semantic_rgb_flatmap: pycortex not importable: %s", exc)
            return {}

        resp_data = context.get("responses", ResponseData)
        surface = resp_data.surface
        transform = resp_data.transform

        # Per-channel normalisation to [0, 255]. Use symmetric scaling around 0
        # so a balanced sign map maps to balanced colour (negative -> dim,
        # positive -> bright).
        rgb_channels = []
        for ch in channels:
            v = projection[ch].astype(np.float32)
            if has_real_mask(resp_data.mask):
                v = unmask_scores(v, resp_data.mask)
            scale = max(abs(np.nanmin(v)), abs(np.nanmax(v)), 1e-9)
            normed = (np.clip(v / scale, -1.0, 1.0) + 1.0) * 0.5 * 255.0
            rgb_channels.append(normed.astype(np.uint8))

        # Optional significance mask -> alpha
        alpha = None
        thresh = opts.get("min_voxel_significance")
        if thresh is not None:
            scores = result.scores.copy()
            if has_real_mask(resp_data.mask):
                scores = unmask_scores(scores, resp_data.mask, fill_value=-np.inf)
            alpha = (scores > float(thresh)).astype(np.uint8) * 255

        try:
            volRGB = cortex.VolumeRGB(
                rgb_channels[0], rgb_channels[1], rgb_channels[2],
                subject=surface, xfmname=transform,
                alpha=alpha,
            )
        except ValueError as exc:
            if "mask" in str(exc).lower():
                logger.warning(
                    "semantic_rgb_flatmap: pycortex mask/voxel mismatch — "
                    "see flatmap warning above. Skipping.")
                return {}
            raise
        except Exception as exc:
            logger.warning(
                "semantic_rgb_flatmap: cortex.VolumeRGB failed: %s", exc)
            return {}

        output_dir = Path(config.get("reporting", {})
                          .get("output_dir", "./results"))
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / opts.get("filename", "semantic_rgb_flatmap.png")
        try:
            quickflat_png(
                str(path), volRGB,
                with_curvature=opts.get("with_curvature", True),
                dpi=opts.get("dpi", 100),
            )
        except Exception as exc:
            logger.warning(
                "semantic_rgb_flatmap: quickflat.make_png failed: %s", exc)
            return {}
        return {"semantic_rgb_flatmap": str(path)}

    def validate_config(self, config: dict) -> list[str]:
        return []


def _resolve_key(ctx, key: str):
    # Literal full-key first ('analysis.semantic_pc_projection'), then walk.
    if ctx.has(key):
        return ctx.get(key)
    parts = key.split(".")
    if not ctx.has(parts[0]):
        return None
    obj = ctx.get(parts[0])
    for part in parts[1:]:
        if obj is None:
            return None
        obj = obj.get(part) if isinstance(obj, dict) else getattr(obj, part, None)
    return obj
