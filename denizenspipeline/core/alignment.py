"""TR alignment utilities for high-rate feature data."""

from __future__ import annotations

import numpy as np


def align_to_trs(
    features: np.ndarray,
    feature_times: np.ndarray,
    tr_times: np.ndarray,
    method: str = "mean",
) -> np.ndarray:
    """Bin high-rate features into TR windows.

    Parameters
    ----------
    features : np.ndarray
        Feature matrix, shape ``(n_samples,)`` or ``(n_samples, n_features)``.
    feature_times : np.ndarray
        Timestamps for each sample in *features* (seconds).
    tr_times : np.ndarray
        TR onset times (seconds).  Each TR window spans from
        ``tr_times[i]`` to ``tr_times[i+1]``; the last window extends to
        the end of *feature_times*.
    method : str
        Aggregation method: ``"mean"`` (default) or ``"sum"``.

    Returns
    -------
    np.ndarray
        Aggregated features, shape ``(n_trs, n_features)``.
    """
    if method not in ("mean", "sum"):
        raise ValueError(f"method must be 'mean' or 'sum', got '{method}'")

    features = np.atleast_2d(features)
    if features.shape[0] == 1 and features.shape[1] == len(feature_times):
        features = features.T  # was (1, n_samples) → (n_samples, 1)

    n_trs = len(tr_times)
    n_features = features.shape[1]
    out = np.zeros((n_trs, n_features), dtype=float)

    # Bin boundaries: each TR window is [tr_times[i], tr_times[i+1])
    # Last window extends to infinity.
    bin_edges = np.append(tr_times, np.inf)
    indices = np.searchsorted(bin_edges, feature_times, side="right") - 1

    for i in range(n_trs):
        mask = indices == i
        if not np.any(mask):
            continue
        if method == "mean":
            out[i] = features[mask].mean(axis=0)
        else:
            out[i] = features[mask].sum(axis=0)

    return out
