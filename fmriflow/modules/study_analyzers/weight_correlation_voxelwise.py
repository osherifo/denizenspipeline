"""WeightCorrelationVoxelwise — Deniz 2019 Fig 6a.

For each subject present in both groups, correlate the per-voxel
delayed weight vectors for one feature (default ``english1000``,
the semantic feature) between the two modalities. Project the
per-voxel correlation onto fsaverage and average across subjects so
the result can be rendered on the common cortical surface.

In Deniz 2019 the rendering colour-saturates voxels by the magnitude
of the within-modality prediction accuracy; that's a reporter-side
concern. This analyzer just produces the mean cross-modality
weight-correlation map.
"""

from __future__ import annotations

import logging

import numpy as np

from fmriflow.core.study_types import StudyResult
from fmriflow.modules._decorators import study_analyzer
from fmriflow.modules.study_analyzers._cross_modal import (
    common_subjects, pearson_per_voxel,
    project_voxel_array_to_fsaverage, slice_feature_weights,
    stack_and_mean_fsaverage,
)
from fmriflow.modules.study_analyzers._helpers import my_cfg

logger = logging.getLogger(__name__)


@study_analyzer("weight_correlation_voxelwise")
class WeightCorrelationVoxelwiseAnalyzer:
    """Cross-modality per-voxel weight correlation, averaged across subjects."""

    name = "weight_correlation_voxelwise"
    produces_group_artifact = False
    PARAM_SCHEMA = {
        "a": {
            "type": "str",
            "description": "First group's study-scope label (e.g. 'reading').",
        },
        "b": {
            "type": "str",
            "description": "Second group's study-scope label (e.g. 'listening').",
        },
        "feature": {
            "type": "str",
            "default": "english1000",
            "description": (
                "Feature whose delayed-weight block to correlate "
                "between the two modalities, per voxel."
            ),
        },
        "output_key": {
            "type": "str",
            "default": "study.weight_correlation_fsaverage_mean",
            "description": (
                "Study-artifact key for the mean per-vertex correlation "
                "in fsaverage space."
            ),
        },
    }

    def analyze(self, study: StudyResult, config: dict) -> None:
        cfg = my_cfg(config, self.name)
        label_a = cfg.get("a")
        label_b = cfg.get("b")
        if not (label_a and label_b):
            raise ValueError(
                "weight_correlation_voxelwise: 'a' and 'b' are required")
        feature = cfg.get("feature", "english1000")
        output_key = cfg.get(
            "output_key", "study.weight_correlation_fsaverage_mean")

        group_a = study.group(label_a)
        group_b = study.group(label_b)
        a_by, b_by, common = common_subjects(group_a, group_b)
        if not common:
            raise ValueError(
                f"weight_correlation_voxelwise: no subjects shared between "
                f"groups '{label_a}' and '{label_b}' (a={list(a_by)}, "
                f"b={list(b_by)})")

        fs_arrays: list[np.ndarray | None] = []
        per_subject: dict[str, dict[str, float]] = {}

        for sub in common:
            sa, sb = a_by[sub], b_by[sub]
            ctx_a, ctx_b = sa.context, sb.context
            if ctx_a is None or ctx_b is None:
                continue
            if not (ctx_a.has("result") and ctx_b.has("result")):
                logger.warning(
                    "weight_correlation_voxelwise: subject %s missing "
                    "'result' in one modality — skipping", sub)
                continue
            from fmriflow.core.types import ModelResult
            r_a = ctx_a.get("result", ModelResult)
            r_b = ctx_b.get("result", ModelResult)
            try:
                block_a = slice_feature_weights(r_a, feature)
                block_b = slice_feature_weights(r_b, feature)
            except KeyError as e:
                logger.warning(
                    "weight_correlation_voxelwise: subject %s: %s — "
                    "skipping", sub, e)
                continue
            if block_a.shape != block_b.shape:
                logger.warning(
                    "weight_correlation_voxelwise: subject %s shape "
                    "mismatch %s vs %s — skipping",
                    sub, block_a.shape, block_b.shape)
                continue

            corr_native = pearson_per_voxel(block_a, block_b)        # (n_voxels,)
            per_subject[sub] = {
                "n_voxels": int(corr_native.shape[0]),
                "mean_corr": float(np.nanmean(corr_native)),
            }
            fs = project_voxel_array_to_fsaverage(corr_native, sa)
            fs_arrays.append(fs)

        mean_fs = stack_and_mean_fsaverage(fs_arrays)
        if mean_fs is None:
            logger.warning(
                "weight_correlation_voxelwise: no subjects successfully "
                "projected to fsaverage — leaving '%s' unset", output_key)
            return
        study.put(output_key, mean_fs)
        study.put(f"{output_key}.meta", {
            "a": label_a, "b": label_b, "feature": feature,
            "n_subjects_kept": sum(1 for a in fs_arrays if a is not None),
            "n_subjects_attempted": len(common),
            "per_subject": per_subject,
            "shape": list(mean_fs.shape),
            "dtype": str(mean_fs.dtype),
        })

    def validate_config(self, config: dict) -> list[str]:
        cfg = my_cfg(config, self.name)
        errors: list[str] = []
        for k in ("a", "b"):
            if not cfg.get(k):
                errors.append(f"weight_correlation_voxelwise.{k} is required")
        return errors
