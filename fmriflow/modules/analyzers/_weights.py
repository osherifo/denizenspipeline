"""Shared helpers for analyzers that slice the delayed weight matrix.

A ridge model's :attr:`fmriflow.core.types.ModelResult.weights` has shape
``(n_delayed_features, n_voxels)`` — features occupy the **first axis**
(rows), one row per (feature × delay) pair, in `feature_names` order.

(The "column" framing you'd see in classical regression refers to the
design matrix ``X`` of shape ``(n_samples, n_delayed_features)``; the
weight matrix is its transpose for this purpose, so what's a column in
``X`` becomes a row in ``W``.)

The same row layout shows up in three places (variance partitioning,
semantic-subspace projection, the planned weight-analysis remap), so
the slicing logic lives here once.
"""

from __future__ import annotations

import numpy as np

from fmriflow.core.types import ModelResult


def feature_row_ranges(result: ModelResult) -> dict[str, tuple[int, int]]:
    """Map feature name → ``(row_start, row_end)`` inside ``result.weights``.

    The slice is along the first axis (``fdim * n_delays`` rows per
    feature). End is exclusive.
    """
    ranges: dict[str, tuple[int, int]] = {}
    row = 0
    n_delays = max(1, len(result.delays))
    for fname, fdim in zip(result.feature_names, result.feature_dims):
        total = int(fdim) * n_delays
        ranges[fname] = (row, row + total)
        row += total
    return ranges


def slice_feature_block(result: ModelResult, feature: str) -> np.ndarray:
    """Return the rows of ``result.weights`` belonging to ``feature``.

    Shape is ``(feature_dim * n_delays, n_voxels)``. Raises ``KeyError``
    with a useful message if ``feature`` is not part of the result.
    """
    ranges = feature_row_ranges(result)
    if feature not in ranges:
        raise KeyError(
            f"Feature '{feature}' not in ModelResult.feature_names="
            f"{result.feature_names}"
        )
    start, end = ranges[feature]
    return result.weights[start:end, :]
