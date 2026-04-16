"""Variance partitioning — unique variance per feature or feature group."""

from __future__ import annotations

import logging

import numpy as np

from fmriflow.core.array_utils import make_delayed
from fmriflow.core.types import (
    ModelResult, PreparedData, VariancePartition,
)
from fmriflow.modules._decorators import analyzer

logger = logging.getLogger(__name__)


@analyzer("variance_partition")
class VariancePartitionAnalyzer:
    """Computes unique variance explained by each feature group.

    Method: for each group, compare full-model R² to the R² of a model
    that zeros out that group's weights. The difference is the unique
    variance attributable to that group.

    Stores result in context as ``analysis.variance_partition``.
    """

    name = "variance_partition"
    PARAM_SCHEMA = {
        "groups": {"type": "dict", "description": "Custom feature groups {group_name: [feature_names]}"},
    }

    def analyze(self, context, config: dict) -> None:
        result = context.get('result', ModelResult)
        prepared = context.get('prepared', PreparedData)
        acfg = self._get_config(config)

        groups = acfg.get('groups')
        if groups:
            group_names = list(groups.keys())
        else:
            # Default: one group per feature
            group_names = list(result.feature_names)
            groups = {fn: [fn] for fn in group_names}

        # Build column index ranges per feature (in delayed space)
        feat_col_ranges = {}
        col = 0
        n_delays = len(result.delays)
        for fname, fdim in zip(result.feature_names, result.feature_dims):
            total = fdim * n_delays
            feat_col_ranges[fname] = (col, col + total)
            col += total

        # Full model predictions and R²
        full_pred = prepared.X_test @ result.weights
        total_var = _r2_per_voxel(prepared.Y_test, full_pred)

        # Per-group unique variance via leave-one-out
        unique_var = np.zeros((len(group_names), result.n_voxels))
        for gi, gname in enumerate(group_names):
            # Zero out columns belonging to this group
            w_ablated = result.weights.copy()
            for fname in groups[gname]:
                if fname in feat_col_ranges:
                    c0, c1 = feat_col_ranges[fname]
                    w_ablated[c0:c1, :] = 0.0

            ablated_pred = prepared.X_test @ w_ablated
            ablated_r2 = _r2_per_voxel(prepared.Y_test, ablated_pred)
            unique_var[gi] = total_var - ablated_r2

        shared_var = total_var - unique_var.sum(axis=0)

        context.put('analysis.variance_partition', VariancePartition(
            unique_variance=unique_var,
            shared_variance=shared_var,
            total_variance=total_var,
            group_names=group_names,
        ))
        logger.info("Variance partition: %d groups, mean total R²=%.4f",
                     len(group_names), np.nanmean(total_var))

    def validate_config(self, config: dict) -> list[str]:
        errors = []
        acfg = self._get_config(config)
        groups = acfg.get('groups')
        if groups is not None and not isinstance(groups, dict):
            errors.append("variance_partition 'groups' must be a dict "
                          "mapping group names to feature name lists")
        return errors

    @staticmethod
    def _get_config(config: dict) -> dict:
        for acfg in config.get('analysis', []):
            if acfg.get('name') == 'variance_partition':
                return acfg.get('params', {})
        return {}


def _r2_per_voxel(Y_true: np.ndarray, Y_pred: np.ndarray) -> np.ndarray:
    """Compute R² (coefficient of determination) per voxel column."""
    ss_res = np.sum((Y_true - Y_pred) ** 2, axis=0)
    ss_tot = np.sum((Y_true - Y_true.mean(axis=0, keepdims=True)) ** 2, axis=0)
    ss_tot = np.where(ss_tot == 0, 1, ss_tot)
    return 1 - ss_res / ss_tot
