"""Shared helpers for analyzers that slice the delayed weight matrix.

A ridge model's :attr:`fmriflow.core.types.ModelResult.weights` has shape
``(n_delayed_features, n_voxels)`` — every feature's columns are tiled
once per delay, in `feature_names` order. The same column layout shows
up in three places (variance partitioning, semantic-subspace projection,
the planned weight-analysis remap), so the slicing logic lives here once.
"""

from __future__ import annotations

import numpy as np

from fmriflow.core.types import ModelResult


def feature_column_ranges(result: ModelResult) -> dict[str, tuple[int, int]]:
    """Map feature name → ``(col_start, col_end)`` inside ``result.weights``.

    The slice is over the **delayed** column axis (``fdim * n_delays``
    columns per feature). End is exclusive.
    """
    ranges: dict[str, tuple[int, int]] = {}
    col = 0
    n_delays = max(1, len(result.delays))
    for fname, fdim in zip(result.feature_names, result.feature_dims):
        total = int(fdim) * n_delays
        ranges[fname] = (col, col + total)
        col += total
    return ranges


def slice_feature_block(result: ModelResult, feature: str) -> np.ndarray:
    """Return the rows of ``result.weights`` belonging to ``feature``.

    Shape is ``(feature_dim * n_delays, n_voxels)``. Raises ``KeyError``
    with a useful message if ``feature`` is not part of the result.
    """
    ranges = feature_column_ranges(result)
    if feature not in ranges:
        raise KeyError(
            f"Feature '{feature}' not in ModelResult.feature_names="
            f"{result.feature_names}"
        )
    start, end = ranges[feature]
    return result.weights[start:end, :]
