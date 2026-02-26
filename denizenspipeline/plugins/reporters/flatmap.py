"""FlatmapReporter — generates pycortex flatmap visualizations."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from denizenspipeline.core.mask_utils import has_real_mask, unmask_scores
from denizenspipeline.core.types import ModelResult, ResponseData

logger = logging.getLogger(__name__)


class FlatmapReporter:
    """Generates pycortex flatmap visualizations.

    Two modes depending on how responses were loaded:

    - **Volumetric pipeline** (real mask on ResponseData): scores are expanded
      back to the full volume via ``unmask_scores`` before passing to
      ``cortex.Volume``.
    - **Pre-masked pipeline** (placeholder mask): scores are passed directly
      to ``cortex.Volume`` which resolves geometry from the transform — the
      same approach as calling ``cortex.Volume(scores, subject, xfm)``
      interactively.

    Per-reporter options (``config['reporting']['flatmap']``):

    - **cmap** (str): Matplotlib colormap name. Default ``"inferno"``.
    - **vmin** / **vmax** (float): Color scale limits. Default ``0`` / ``0.5``.
    - **with_curvature** (bool): Overlay curvature. Default ``True``.
    - **threshold** (float | None): Mask scores below this to NaN.
    - **dpi** (int): PNG resolution. Default ``100``.
    """

    name = "flatmap"

    def report(self, result: ModelResult, context, config: dict) -> dict[str, str]:
        import cortex

        resp_data = context.get('responses', ResponseData)
        output_dir = Path(config.get('reporting', {}).get('output_dir', './results'))
        output_dir.mkdir(parents=True, exist_ok=True)

        opts = config.get('reporting', {}).get('flatmap', {})
        cmap = opts.get('cmap', 'inferno')
        vmin = opts.get('vmin', 0)
        vmax = opts.get('vmax', 0.5)
        with_curvature = opts.get('with_curvature', True)
        threshold = opts.get('threshold', None)
        dpi = opts.get('dpi', 100)

        scores = result.scores.copy()

        if threshold is not None:
            scores[scores < threshold] = np.nan

        if has_real_mask(resp_data.mask):
            # Volumetric: expand masked scores back to full volume
            scores = unmask_scores(scores, resp_data.mask)

        # cortex.Volume accepts both full-volume and pre-masked 1-D arrays;
        # the transform defines the geometry in either case.
        vol = cortex.Volume(
            scores,
            resp_data.surface,
            resp_data.transform,
            vmin=vmin, vmax=vmax, cmap=cmap,
        )

        path = output_dir / 'prediction_accuracy_flatmap.png'
        cortex.quickflat.make_png(
            str(path), vol,
            with_curvature=with_curvature,
            dpi=dpi,
        )

        return {'flatmap': str(path)}

    def validate_config(self, config: dict) -> list[str]:
        return []
