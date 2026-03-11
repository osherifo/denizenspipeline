"""FlatmapMappedReporter — flatmap via pre-computed sparse mapper."""

from __future__ import annotations

import logging
from pathlib import Path

import h5py
import matplotlib.pyplot as plt
import numpy as np
from scipy.sparse import csr_matrix

from denizenspipeline.core.types import ModelResult
from denizenspipeline.plugins._decorators import reporter

logger = logging.getLogger(__name__)


@reporter("flatmap_mapped")
class FlatmapMappedReporter:
    """Generates flatmap images using a pre-computed voxel-to-flatmap mapper.

    Bypasses pycortex entirely by loading a sparse CSR matrix from an HDF
    file that projects voxel scores directly into flatmap pixel space.

    Per-reporter options (``config['reporting']['flatmap_mapped']``):

    - **mapper_path** (str, required): Path to HDF file with mapper data.
    - **cmap** (str): Matplotlib colormap name. Default ``"inferno"``.
    - **vmin** / **vmax** (float): Color scale limits. Default ``0`` / ``0.5``.
    - **threshold** (float | None): Mask scores below this to NaN.
    - **dpi** (int): PNG resolution. Default ``100``.
    """

    name = "flatmap_mapped"
    PARAM_SCHEMA = {
        "mapper_path": {"type": "path", "required": True, "description": "Path to HDF file with sparse CSR mapper"},
        "cmap": {"type": "string", "default": "inferno", "description": "Matplotlib colormap"},
        "vmin": {"type": "float", "default": 0.0, "description": "Color scale minimum"},
        "vmax": {"type": "float", "default": 0.5, "description": "Color scale maximum"},
        "threshold": {"type": "float", "description": "Mask scores below this value"},
        "dpi": {"type": "int", "default": 100, "min": 50, "description": "PNG resolution"},
    }

    def report(self, result: ModelResult, context, config: dict) -> dict[str, str]:
        output_dir = Path(config.get('reporting', {}).get('output_dir', './results'))
        output_dir.mkdir(parents=True, exist_ok=True)

        opts = config.get('reporting', {}).get('flatmap_mapped', {})
        mapper_path = opts.get('mapper_path')
        if not mapper_path:
            logger.error("flatmap_mapped: 'mapper_path' not set in config")
            return {}

        cmap = opts.get('cmap', 'inferno')
        vmin = opts.get('vmin', 0)
        vmax = opts.get('vmax', 0.5)
        threshold = opts.get('threshold', None)
        dpi = opts.get('dpi', 100)

        # --- Load mapper from HDF ---
        mapper_path = Path(mapper_path)
        if not mapper_path.exists():
            logger.error("flatmap_mapped: mapper file not found: %s", mapper_path)
            return {}

        with h5py.File(mapper_path, 'r') as f:
            data = f['voxel_to_flatmap_data'][:]
            indices = f['voxel_to_flatmap_indices'][:]
            indptr = f['voxel_to_flatmap_indptr'][:]
            shape = tuple(f['voxel_to_flatmap_shape'][:])
            flatmap_mask = f['flatmap_mask'][:].astype(bool)
            curvature = f['flatmap_curvature'][:]

        mapper = csr_matrix((data, indices, indptr), shape=shape)

        # --- Prepare scores ---
        scores = result.scores.copy()
        n_voxels = scores.shape[0]

        if mapper.shape[1] != n_voxels:
            logger.error(
                "flatmap_mapped: mapper expects %d voxels but scores have %d",
                mapper.shape[1], n_voxels,
            )
            return {}

        if threshold is not None:
            scores[scores < threshold] = np.nan

        # --- Project to flatmap pixels ---
        # For thresholded scores with NaN: treat NaN as 0 for projection,
        # then restore NaN where all contributing voxels were NaN.
        has_nan = np.any(np.isnan(scores))
        if has_nan:
            scores_clean = np.where(np.isnan(scores), 0, scores)
            pixel_values = np.asarray(mapper @ scores_clean).ravel()
            # Mark pixels as NaN if they got zero contribution
            nan_mask_vox = np.isnan(result.scores.copy())
            if threshold is not None:
                nan_mask_vox |= result.scores < threshold
            contrib = np.asarray(mapper @ (~nan_mask_vox).astype(float)).ravel()
            pixel_values[contrib == 0] = np.nan
        else:
            pixel_values = np.asarray(mapper @ scores).ravel()

        # --- Build 2D image ---
        h, w = flatmap_mask.shape
        image = np.full((h, w), np.nan, dtype=float)
        image[flatmap_mask] = pixel_values

        # --- Render ---
        fig, ax = plt.subplots(1, 1, figsize=(w / 100, h / 100), dpi=dpi)
        ax.imshow(curvature, cmap='gray', vmin=-1, vmax=1)
        alpha = (~np.isnan(image)).astype(np.float32)
        im = ax.imshow(image, cmap=cmap, vmin=vmin, vmax=vmax, alpha=alpha)
        ax.axis('off')
        fig.colorbar(im, ax=ax, fraction=0.025, pad=0.02)

        path = output_dir / 'prediction_accuracy_flatmap.png'
        fig.savefig(str(path), dpi=dpi, bbox_inches='tight', facecolor='white')
        plt.close(fig)

        logger.info("flatmap_mapped: saved %s", path)
        return {'flatmap_mapped': str(path)}

    def validate_config(self, config: dict) -> list[str]:
        errors = []
        opts = config.get('reporting', {}).get('flatmap_mapped', {})
        if not opts.get('mapper_path'):
            errors.append("reporting.flatmap_mapped.mapper_path is required")
        return errors
