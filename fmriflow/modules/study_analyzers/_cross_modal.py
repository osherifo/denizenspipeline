"""Shared helpers for the cross-modality study analyzers.

The four analyzers (``weight_correlation_voxelwise``,
``semantic_pc_correlation``, ``cross_modal_prediction``,
``cross_within_summary``) all need to:

* index each group's subjects by name and intersect the two sets;
* slice a single feature's weight block from a :class:`ModelResult`
  (rows) and the matching column range from
  :class:`PreparedData.X_test` (columns);
* project a per-voxel native-space array onto fsaverage so the per-
  subject results can be averaged.

Keeping the slicing / projection helpers here avoids copy-paste across
five plugin files.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Iterable

import numpy as np

from fmriflow.core.group_types import GroupResult, SubjectResult
from fmriflow.core.types import ModelResult, PreparedData, ResponseData
from fmriflow.modules.analyzers._weights import slice_feature_block

logger = logging.getLogger(__name__)


def common_subjects(
    group_a: GroupResult, group_b: GroupResult,
) -> tuple[dict[str, SubjectResult], dict[str, SubjectResult], list[str]]:
    """Index each group's subjects by name; return per-group dicts and
    the sorted list of subjects present in both with an in-memory
    context. Subjects without a context (resumed-from-disk runs) can't
    be cross-correlated; they are dropped with a warning naming them."""
    dropped = sorted({sr.subject for sr in (*group_a.subjects, *group_b.subjects)
                      if sr.context is None})
    if dropped:
        logger.warning(
            "Left out of the cross-group comparison (no in-memory results, "
            "resumed from disk): %s", ', '.join(dropped))
    a_by = {sr.subject: sr for sr in group_a.subjects if sr.context is not None}
    b_by = {sr.subject: sr for sr in group_b.subjects if sr.context is not None}
    return a_by, b_by, sorted(set(a_by) & set(b_by))


def feature_col_range(prepared: PreparedData, feature: str) -> tuple[int, int]:
    """Return the (start, end) **column** range in ``prepared.X_test`` /
    ``X_train`` belonging to *feature*. Mirrors
    :func:`slice_feature_block` but acts on the design matrix (which
    is the weight matrix's transpose for the feature axis).
    """
    n_delays = max(1, len(prepared.delays))
    col = 0
    for fname, fdim in zip(prepared.feature_names, prepared.feature_dims):
        total = int(fdim) * n_delays
        if fname == feature:
            return col, col + total
        col += total
    raise KeyError(
        f"Feature '{feature}' not in PreparedData.feature_names="
        f"{prepared.feature_names}")


def pearson_per_voxel(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Per-column Pearson correlation between two ``(n_rows, n_cols)``
    matrices. Returns shape ``(n_cols,)``. NaN where one column has
    zero variance."""
    if a.shape != b.shape:
        raise ValueError(
            f"pearson_per_voxel: shape mismatch {a.shape} vs {b.shape}")
    a = a.astype(np.float64, copy=False)
    b = b.astype(np.float64, copy=False)
    a = a - a.mean(axis=0, keepdims=True)
    b = b - b.mean(axis=0, keepdims=True)
    num = (a * b).sum(axis=0)
    den = np.sqrt((a * a).sum(axis=0) * (b * b).sum(axis=0))
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(den > 0, num / den, np.nan)


def project_voxel_array_to_fsaverage(
    arr: np.ndarray, subject_result: SubjectResult, *,
    fs_subject: str | None = None, subjects_dir: str | None = None,
) -> np.ndarray | None:
    """Project a flat per-voxel array onto fsaverage using the same
    pycortex + FreeSurfer pipeline as the subject-scope
    :class:`ProjectToFsaverageAnalyzer`.

    Returns ``None`` (with a warning logged) if pycortex, FreeSurfer,
    or the subject's transforms aren't available — letting the study
    analyzer keep going on whatever subjects do project successfully.
    """
    # Late import so a missing pycortex doesn't break the module load.
    from fmriflow.modules.analyzers.project_to_fsaverage import (
        _SkipFsaverage, _project_to_fsaverage,
    )
    ctx = subject_result.context
    if ctx is None or not ctx.has("responses"):
        logger.warning(
            "project_voxel_array_to_fsaverage: subject %s has no responses "
            "in context — skipping", subject_result.subject)
        return None
    resp = ctx.get("responses", ResponseData)
    try:
        return _project_to_fsaverage(
            np.asarray(arr).astype(np.float32),
            surface=resp.surface, transform=resp.transform,
            fs_subject=fs_subject or resp.surface,
            subjects_dir=subjects_dir or os.environ.get("SUBJECTS_DIR"),
            resp_mask=resp.mask,
        )
    except _SkipFsaverage as exc:
        logger.warning(
            "project_voxel_array_to_fsaverage: skipped %s (%s)",
            subject_result.subject, exc)
        return None


def stack_and_mean_fsaverage(
    fs_arrays: Iterable[np.ndarray | None],
) -> np.ndarray | None:
    """Stack the per-subject fsaverage arrays (dropping Nones), return
    the per-vertex mean. Returns ``None`` if everything was skipped."""
    kept = [a for a in fs_arrays if a is not None]
    if not kept:
        return None
    stacked = np.stack(kept, axis=0)
    return np.nanmean(stacked, axis=0)


def best_predicted_voxels(
    result_a: ModelResult, result_b: ModelResult, k: int,
) -> np.ndarray:
    """Indices of the top-K voxels by mean(within-modality prediction
    accuracy). Used to restrict per-PC correlations to voxels where
    both modalities have reliable signal, suppressing PC-correlation
    noise driven by poorly-predicted voxels."""
    if result_a.scores.shape != result_b.scores.shape:
        raise ValueError(
            "best_predicted_voxels: subject's two modalities have "
            f"differing voxel counts {result_a.scores.shape} vs "
            f"{result_b.scores.shape}")
    mean_acc = 0.5 * (result_a.scores + result_b.scores)
    k = min(k, mean_acc.shape[0])
    return np.argsort(-mean_acc)[:k]


def pull_result_and_prepared(
    sr: SubjectResult,
) -> tuple[ModelResult, PreparedData] | None:
    """Pull both ``result`` and ``prepared`` from a subject's context.
    Returns None (with warning) if either is missing."""
    ctx = sr.context
    if ctx is None:
        return None
    if not (ctx.has("result") and ctx.has("prepared")):
        logger.warning(
            "subject %s missing 'result' or 'prepared' in context — "
            "skipping", sr.subject)
        return None
    return ctx.get("result", ModelResult), ctx.get("prepared", PreparedData)


def slice_feature_x_test(
    prepared: PreparedData, feature: str,
) -> np.ndarray:
    """Return the columns of ``X_test`` belonging to *feature*. Used by
    cross-modal prediction to apply one modality's semantic weights to
    the other modality's test features."""
    start, end = feature_col_range(prepared, feature)
    return prepared.X_test[:, start:end]


def slice_feature_weights(
    result: ModelResult, feature: str,
) -> np.ndarray:
    """Thin re-export of :func:`slice_feature_block` for symmetry with
    :func:`slice_feature_x_test`."""
    return slice_feature_block(result, feature)
