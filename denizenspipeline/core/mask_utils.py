"""Utilities for expanding masked voxel scores back to full volume shape."""

from __future__ import annotations

import numpy as np


def has_real_mask(mask: np.ndarray) -> bool:
    """Return True if mask is not the placeholder ``np.array([True])``."""
    return not (mask.shape == (1,) and mask.dtype == bool and mask.all())


def unmask_scores(
    scores: np.ndarray,
    mask: np.ndarray,
    fill_value: float = np.nan,
) -> np.ndarray:
    """Place masked voxel scores into full volume at mask positions.

    Parameters
    ----------
    scores : np.ndarray, shape (n_masked,)
        Per-voxel scores in masked (compressed) space.
    mask : np.ndarray
        Boolean mask of shape ``(x, y, z)`` or 1-D. If the placeholder
        ``np.array([True])`` is passed, *scores* are returned unchanged.
    fill_value : float
        Value for voxels outside the mask. Default ``np.nan``.

    Returns
    -------
    np.ndarray
        Full-volume array with *scores* placed at mask positions.
    """
    if not has_real_mask(mask):
        return scores

    full = np.full(mask.shape, fill_value, dtype=scores.dtype)
    full[mask] = scores
    return full
