"""WebGLReporter — pycortex interactive 3D viewer as static HTML."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from denizenspipeline.core.mask_utils import has_real_mask, unmask_scores
from denizenspipeline.core.types import ModelResult, ResponseData

logger = logging.getLogger(__name__)


class WebGLReporter:
    """Generates an interactive pycortex WebGL viewer as static HTML.

    Handles both volumetric (unmask → full volume) and pre-masked (scores
    passed directly) pipelines, same as :class:`FlatmapReporter`.

    Per-reporter options (``config['reporting']['webgl']``):

    - **cmap** (str): Matplotlib colormap name. Default ``"inferno"``.
    - **vmin** / **vmax** (float): Color scale limits. Default ``0`` / ``0.5``.
    - **open_browser** (bool): Open viewer in browser. Default ``False``.
    - **threshold** (float | None): Mask scores below this to NaN.
    """

    name = "webgl"

    def report(self, result: ModelResult, context, config: dict) -> dict[str, str]:
        import cortex

        resp_data = context.get('responses', ResponseData)
        output_dir = Path(config.get('reporting', {}).get('output_dir', './results'))
        output_dir.mkdir(parents=True, exist_ok=True)

        opts = config.get('reporting', {}).get('webgl', {})
        cmap = opts.get('cmap', 'inferno')
        vmin = opts.get('vmin', 0)
        vmax = opts.get('vmax', 0.5)
        open_browser = opts.get('open_browser', False)
        threshold = opts.get('threshold', None)

        scores = result.scores.copy()

        if threshold is not None:
            scores[scores < threshold] = np.nan

        if has_real_mask(resp_data.mask):
            scores = unmask_scores(scores, resp_data.mask)

        vol = cortex.Volume(
            scores,
            resp_data.surface,
            resp_data.transform,
            vmin=vmin, vmax=vmax, cmap=cmap,
        )

        viewer_dir = output_dir / 'webgl_viewer'
        cortex.webgl.make_static(
            str(viewer_dir),
            vol,
            recache=False,
        )

        if open_browser:
            import webbrowser
            webbrowser.open(str(viewer_dir / 'index.html'))

        return {'webgl': str(viewer_dir)}

    def validate_config(self, config: dict) -> list[str]:
        return []
