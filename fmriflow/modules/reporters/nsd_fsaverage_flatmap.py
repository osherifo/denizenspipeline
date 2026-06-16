"""NsdFsaverageFlatmapReporter — flatmap of func-volume scores on fsaverage.

NSD analyses run in the subject's 1.8 mm functional volume, but pycortex ships a
flattened ``fsaverage`` surface, so no per-subject surface registration or
flattening is needed to visualise results.  This reporter:

1. expands the masked voxel scores back into the full func1pt8mm volume,
2. samples them onto the subject's native white surface using NSD's
   ``{hemi}.func1pt8-to-white.mgz`` voxel-coordinate maps,
3. resamples native -> fsaverage with ``{hemi}.white-to-fsaverage.mgz``,
4. renders a ``cortex.Vertex`` quickflat on fsaverage.

The volume->surface convention (direct (i,j,k) axis order, 1-based coordinates)
is validated in ``testing/nsd/verify_surface_mapping.py`` against NSD's official
fsaverage nsdgeneral label (Dice ~0.85).
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from fmriflow.core.mask_utils import has_real_mask, unmask_scores
from fmriflow.core.types import ModelResult, ResponseData
from fmriflow.modules._decorators import reporter

logger = logging.getLogger(__name__)


@reporter("nsd_fsaverage_flatmap")
class NsdFsaverageFlatmapReporter:
    """Render func1pt8mm voxel scores as an fsaverage flatmap."""

    name = "nsd_fsaverage_flatmap"
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
        if not has_real_mask(resp_data.mask):
            logger.warning("nsd_fsaverage_flatmap needs the 3-D ROI mask on "
                           "ResponseData (use the nsd response loader); skipping.")
            return {}

        resp_cfg = config.get('response', {})
        raw_dir = Path(resp_cfg.get('raw_dir', '.'))
        subject = resp_cfg.get('subject') or config.get('subject')
        tf_dir = raw_dir / "nsddata" / "ppdata" / subject / "transforms"

        opts = config.get('reporting', {}).get(self.name, {})
        output_dir = Path(config.get('reporting', {}).get('output_dir', './results'))
        output_dir.mkdir(parents=True, exist_ok=True)

        # Expand masked scores to the full func1pt8mm volume.
        full_vol = unmask_scores(result.scores.astype(float), resp_data.mask)
        threshold = opts.get('threshold', None)

        verts = np.concatenate([
            self._volume_to_fsaverage(full_vol, resp_data.mask, tf_dir, h)
            for h in ("lh", "rh")
        ])
        if threshold is not None:
            verts[verts < threshold] = np.nan

        vx = cortex.Vertex(
            verts, opts.get('fsaverage_subject', 'fsaverage'),
            vmin=opts.get('vmin', 0.0), vmax=opts.get('vmax', 0.5),
            cmap=opts.get('cmap', 'inferno'),
        )
        path = output_dir / opts.get('filename', 'prediction_accuracy_fsaverage_flatmap.png')
        cortex.quickflat.make_png(
            str(path), vx,
            with_curvature=opts.get('with_curvature', True),
            dpi=opts.get('dpi', 100),
        )
        return {self.name: str(path)}

    @staticmethod
    def _volume_to_fsaverage(full_vol, mask_3d, tf_dir, hemi):
        """Sample a func1pt8mm volume onto fsaverage vertices for one hemisphere."""
        import nibabel as nib
        from scipy.ndimage import map_coordinates

        f2w = np.asarray(nib.load(tf_dir / f"{hemi}.func1pt8-to-white.mgz").dataobj)
        w2f = np.asarray(nib.load(tf_dir / f"{hemi}.white-to-fsaverage.mgz").dataobj)
        coords = f2w.reshape(-1, 3).T - 1.0   # (3, n_white), 1-based -> 0-based
        idx = w2f.reshape(-1).astype(int) - 1  # 1-based native-white index

        # Trilinear within the ROI; NaN outside so curvature shows through.
        filled = np.nan_to_num(full_vol, nan=0.0)
        vals = map_coordinates(filled, coords, order=1, mode="nearest")
        inmask = map_coordinates(mask_3d.astype(float), coords, order=1,
                                 mode="nearest") > 0.5
        vals = np.where(inmask, vals, np.nan)
        return vals[idx]

    def validate_config(self, config: dict) -> list[str]:
        return []
