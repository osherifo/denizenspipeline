"""NativeFlatmapReporter — render scores on the subject's *native* cortical
surface using a chosen pycortex transform.

This is the native-space counterpart to ``fsaverage_flatmap``. It wraps the
model scores in ``cortex.Volume(scores, surface, transform)`` and renders a
quickflat PNG — exactly the geometry produced by the ``pycortex_transform``
step (default transform name ``fmriflow``).

Per-reporter options (``config['reporting']['native_flatmap']``):

- **transform** (str): pycortex transform name to render with. Defaults to the
  transform on the loaded ``ResponseData`` (i.e. ``subject_config.transform``).
  Set this to render with a specific xfm (e.g. ``"fmriflow"``) regardless of
  what the loader recorded.
- **cmap** / **vmin** / **vmax** / **with_curvature** / **threshold** / **dpi**:
  as in the ``flatmap`` reporter.
- **filename** (str): output PNG name. Default ``"native_flatmap.png"``.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from fmriflow.core.mask_utils import has_real_mask, unmask_scores
from fmriflow.core.types import ModelResult, ResponseData
from fmriflow.modules._decorators import reporter

logger = logging.getLogger(__name__)


@reporter("native_flatmap")
class NativeFlatmapReporter:
    """Render prediction scores on the native surface via a pycortex transform."""

    name = "native_flatmap"
    PARAM_SCHEMA = {
        "transform": {"type": "string", "description": "Pycortex transform name (default: ResponseData.transform)"},
        "cmap": {"type": "string", "default": "inferno", "description": "Matplotlib colormap"},
        "vmin": {"type": "float", "default": 0.0, "description": "Color scale minimum"},
        "vmax": {"type": "float", "default": 0.5, "description": "Color scale maximum"},
        "with_curvature": {"type": "bool", "default": True, "description": "Overlay cortical curvature"},
        "threshold": {"type": "float", "description": "Mask scores below this value"},
        "dpi": {"type": "int", "default": 100, "min": 50, "description": "PNG resolution"},
        "filename": {"type": "string", "default": "native_flatmap.png", "description": "Output PNG name"},
    }

    def report(self, result: ModelResult, context, config: dict) -> dict[str, str]:
        import cortex

        resp_data = context.get("responses", ResponseData)
        output_dir = Path(config.get("reporting", {}).get("output_dir", "./results"))
        output_dir.mkdir(parents=True, exist_ok=True)

        opts = config.get("reporting", {}).get("native_flatmap", {})
        surface = resp_data.surface
        # Explicit override wins; otherwise use the transform the loader recorded.
        transform = opts.get("transform") or resp_data.transform
        cmap = opts.get("cmap", "inferno")
        vmin = opts.get("vmin", 0.0)
        vmax = opts.get("vmax", 0.5)
        with_curvature = opts.get("with_curvature", True)
        threshold = opts.get("threshold", None)
        dpi = opts.get("dpi", 100)
        filename = opts.get("filename", "native_flatmap.png")

        if not surface or not transform or transform == "unknown":
            logger.warning(
                "native_flatmap: missing surface/transform (surface=%r transform=%r) — skipping.",
                surface, transform,
            )
            return {}

        scores = result.scores.copy()
        if threshold is not None:
            scores[scores < threshold] = np.nan

        if has_real_mask(resp_data.mask):
            scores = unmask_scores(scores, resp_data.mask)

        try:
            vol = cortex.Volume(
                scores, surface, transform,
                vmin=vmin, vmax=vmax, cmap=cmap,
            )
        except ValueError as exc:
            if "mask" in str(exc).lower():
                n_scores = scores.shape[-1] if scores.ndim > 1 else scores.shape[0]
                try:
                    n_mask = int(cortex.db.get_mask(surface, transform, "thick").sum())
                except Exception:
                    n_mask = "?"
                logger.warning(
                    "native_flatmap skipped: score array has %s voxels but pycortex "
                    "mask for %s/%s has %s (geometry mismatch — see error KB 0035).",
                    n_scores, surface, transform, n_mask,
                )
                return {}
            raise

        path = output_dir / filename
        cortex.quickflat.make_png(
            str(path), vol, with_curvature=with_curvature, dpi=dpi,
        )
        logger.info("native_flatmap: wrote %s (surface=%s transform=%s)", path, surface, transform)
        return {"native_flatmap": str(path)}

    def validate_config(self, config: dict) -> list[str]:
        return []
