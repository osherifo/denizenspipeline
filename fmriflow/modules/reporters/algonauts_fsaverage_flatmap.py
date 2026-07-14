"""AlgonautsFsaverageFlatmapReporter — flatmap of Algonauts 2023 vertex scores.

Algonauts 2023 responses already live on the fsaverage surface (in "challenge
space" — the subset of vertices with valid data), so no volume→surface sampling
is needed.  This reporter:

1. splits the per-vertex scores back into left/right hemispheres,
2. expands each hemisphere's challenge-space scores onto the full fsaverage
   surface using the ``{hemi}.all-vertices_fsaverage_space`` masks carried on
   ``ResponseData.metadata['fsaverage_masks']``,
3. renders a ``cortex.Vertex`` quickflat on fsaverage.

Requires the ``algonauts2023`` response loader (which supplies the masks and the
per-hemisphere vertex counts).
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from fmriflow.core.types import ModelResult, ResponseData
from fmriflow.modules._decorators import reporter

logger = logging.getLogger(__name__)


@reporter("algonauts_fsaverage_flatmap")
class AlgonautsFsaverageFlatmapReporter:
    """Render Algonauts 2023 challenge-space vertex scores as an fsaverage flatmap."""

    name = "algonauts_fsaverage_flatmap"
    PARAM_SCHEMA = {
        "cmap": {"type": "string", "default": "inferno", "description": "Matplotlib colormap"},
        "vmin": {"type": "float", "default": 0.0, "description": "Color scale minimum"},
        "vmax": {"type": "float", "default": 0.5, "description": "Color scale maximum"},
        "with_curvature": {"type": "bool", "default": True, "description": "Overlay cortical curvature"},
        "threshold": {"type": "float", "description": "Mask scores below this value"},
        "dpi": {"type": "int", "default": 100, "min": 50, "description": "PNG resolution"},
        "fsaverage_subject": {"type": "string", "default": "fsaverage", "description": "pycortex subject for the fsaverage surface"},
        "filename": {"type": "string", "default": "prediction_accuracy_fsaverage_flatmap.png", "description": "Output PNG filename"},
    }

    def report(self, result: ModelResult, context, config: dict) -> dict[str, str]:
        import cortex

        resp_data = context.get('responses', ResponseData)
        meta = resp_data.metadata
        masks = meta.get('fsaverage_masks', {})
        hemi_dims = meta.get('hemi_dims', {})
        hemis = meta.get('hemispheres', ['lh', 'rh'])
        if not masks or not hemi_dims:
            logger.warning("algonauts_fsaverage_flatmap needs the algonauts2023 "
                           "response loader (fsaverage_masks + hemi_dims); skipping.")
            return {}

        opts = config.get('reporting', {}).get(self.name, {})
        output_dir = Path(config.get('reporting', {}).get('output_dir', './results'))
        output_dir.mkdir(parents=True, exist_ok=True)

        scores = np.asarray(result.scores, dtype=float)
        threshold = opts.get('threshold', None)

        # The loader only carries masks for hemispheres whose mask file exists;
        # bail clearly if any hemisphere or the score length is inconsistent
        # rather than KeyError-ing or misrendering a truncated slice.
        missing = [h for h in hemis if h not in masks or h not in hemi_dims]
        if missing:
            logger.warning("algonauts_fsaverage_flatmap: missing fsaverage_masks/"
                           "hemi_dims for %s; skipping.", missing)
            return {}
        total = sum(hemi_dims[h] for h in hemis)
        if scores.shape[0] != total:
            logger.warning("algonauts_fsaverage_flatmap: scores length %d != "
                           "sum(hemi_dims) %d; skipping.", scores.shape[0], total)
            return {}

        # Split concatenated scores by hemisphere, expand each to full fsaverage.
        verts, offset = [], 0
        for h in hemis:
            d = hemi_dims[h]
            hemi_scores = scores[offset:offset + d]
            offset += d
            full = np.full(masks[h].shape[0], np.nan, dtype=float)
            full[masks[h]] = hemi_scores
            verts.append(full)
        all_verts = np.concatenate(verts)   # lh then rh -> fsaverage
        if threshold is not None:
            all_verts[all_verts < threshold] = np.nan

        vx = cortex.Vertex(
            all_verts, opts.get('fsaverage_subject', 'fsaverage'),
            vmin=opts.get('vmin', 0.0), vmax=opts.get('vmax', 0.5),
            cmap=opts.get('cmap', 'inferno'),
        )
        path = output_dir / opts.get('filename', 'prediction_accuracy_fsaverage_flatmap.png')
        kwargs = dict(with_curvature=opts.get('with_curvature', True), dpi=opts.get('dpi', 100))
        try:
            cortex.quickflat.make_png(str(path), vx, **kwargs)
        except RuntimeError as e:
            # pycortex's ROI/label overlays need inkscape; if it's absent, render
            # the curvature + data layers without overlays rather than failing.
            if 'inkscape' not in str(e).lower():
                raise
            logger.warning("inkscape not available — rendering flatmap without ROI overlays")
            cortex.quickflat.make_png(str(path), vx, with_rois=False, with_labels=False, **kwargs)
        return {self.name: str(path)}

    def validate_config(self, config: dict) -> list[str]:
        return []
