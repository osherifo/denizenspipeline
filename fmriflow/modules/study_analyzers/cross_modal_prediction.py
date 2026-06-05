"""CrossModalPrediction — Deniz 2019 Figs 7 + 8.

For each subject in both groups:

* slice the chosen feature's weight rows from group A's
  :class:`ModelResult` and the matching column block from group B's
  :class:`PreparedData.X_test`;
* compute ``y_pred = X_test_B @ W_A`` (the paper's
  "estimated semantic model weights from listening predicting
  reading responses" — and vice versa);
* score per voxel by Pearson r against the held-out
  ``Y_test`` recorded in group B's prepared data;
* project the per-voxel accuracy onto fsaverage and average across
  subjects so the result lands on the common surface.

One analyzer call writes one direction (A→B); list it twice in
``study_analyze:`` to cover both directions for Figs 7 (listening→reading)
and 8 (reading→listening).
"""

from __future__ import annotations

import logging

import numpy as np

from fmriflow.core.study_types import StudyResult
from fmriflow.modules._decorators import study_analyzer
from fmriflow.modules.study_analyzers._cross_modal import (
    common_subjects, pearson_per_voxel, project_voxel_array_to_fsaverage,
    pull_result_and_prepared, slice_feature_weights, slice_feature_x_test,
    stack_and_mean_fsaverage,
)
from fmriflow.modules.study_analyzers._helpers import my_cfg

logger = logging.getLogger(__name__)


@study_analyzer("cross_modal_prediction")
class CrossModalPredictionAnalyzer:
    """A→B cross-modal prediction accuracy on fsaverage, averaged across subjects."""

    name = "cross_modal_prediction"
    produces_group_artifact = False
    PARAM_SCHEMA = {
        "weights_from": {
            "type": "str",
            "description": (
                "Group whose ModelResult.weights are applied (the "
                "model side of the prediction)."
            ),
        },
        "features_from": {
            "type": "str",
            "description": (
                "Group whose PreparedData.X_test supplies the test "
                "features AND whose Y_test serves as ground truth."
            ),
        },
        "feature": {
            "type": "str",
            "default": "english1000",
            "description": (
                "Feature whose weight block + X_test columns to use. "
                "Defaults to the semantic feature, matching the paper "
                "which used only the semantic model for cross-modal "
                "predictions."
            ),
        },
        "output_key": {
            "type": "str",
            "description": (
                "Study-artifact key for the mean fsaverage prediction "
                "accuracy. Defaults to "
                "'study.cross_pred.<weights_from>_to_<features_from>'."
            ),
        },
    }

    def analyze(self, study: StudyResult, config: dict) -> None:
        cfg = my_cfg(config, self.name)
        wf = cfg.get("weights_from")
        ff = cfg.get("features_from")
        if not (wf and ff):
            raise ValueError(
                "cross_modal_prediction: 'weights_from' and 'features_from' "
                "are required")
        if wf == ff:
            raise ValueError(
                "cross_modal_prediction: 'weights_from' and "
                "'features_from' must differ (within-modality "
                "predictions already live in each group's result)")
        feature = cfg.get("feature", "english1000")
        output_key = cfg.get(
            "output_key", f"study.cross_pred.{wf}_to_{ff}")

        group_w = study.group(wf)
        group_f = study.group(ff)
        w_by, f_by, common = common_subjects(group_w, group_f)
        if not common:
            raise ValueError(
                f"cross_modal_prediction: no shared subjects between "
                f"'{wf}' and '{ff}'")

        fs_arrays: list[np.ndarray | None] = []
        per_subject: dict[str, dict[str, float]] = {}

        for sub in common:
            sw, sf = w_by[sub], f_by[sub]
            packed_w = pull_result_and_prepared(sw)
            packed_f = pull_result_and_prepared(sf)
            if packed_w is None or packed_f is None:
                continue
            result_w, _prepared_w = packed_w
            _result_f, prepared_f = packed_f
            try:
                W = slice_feature_weights(result_w, feature)    # (n_delays*fdim, n_voxels_w)
                X = slice_feature_x_test(prepared_f, feature)    # (n_test_trs, n_delays*fdim)
            except KeyError as exc:
                logger.warning(
                    "cross_modal_prediction: subject %s: %s — skipping",
                    sub, exc)
                continue
            if X.shape[1] != W.shape[0]:
                logger.warning(
                    "cross_modal_prediction: subject %s feature-block "
                    "size mismatch X.cols=%d vs W.rows=%d — skipping",
                    sub, X.shape[1], W.shape[0])
                continue
            Y = prepared_f.Y_test
            if Y is None:
                logger.warning(
                    "cross_modal_prediction: subject %s features_from "
                    "group has no Y_test — skipping", sub)
                continue
            if Y.shape[1] != W.shape[1]:
                logger.warning(
                    "cross_modal_prediction: subject %s voxel mismatch "
                    "Y.cols=%d vs W.cols=%d — skipping",
                    sub, Y.shape[1], W.shape[1])
                continue

            y_pred = X @ W                                  # (n_test_trs, n_voxels)
            r_per_voxel = pearson_per_voxel(y_pred, Y)      # (n_voxels,)
            per_subject[sub] = {
                "n_voxels": int(r_per_voxel.shape[0]),
                "mean_r": float(np.nanmean(r_per_voxel)),
                "median_r": float(np.nanmedian(r_per_voxel)),
            }
            fs = project_voxel_array_to_fsaverage(r_per_voxel, sf)
            fs_arrays.append(fs)

        mean_fs = stack_and_mean_fsaverage(fs_arrays)
        if mean_fs is None:
            logger.warning(
                "cross_modal_prediction: no subjects projected to "
                "fsaverage — leaving '%s' unset", output_key)
            return
        study.put(output_key, mean_fs)
        study.put(f"{output_key}.meta", {
            "weights_from": wf, "features_from": ff,
            "feature": feature,
            "n_subjects_kept": sum(1 for a in fs_arrays if a is not None),
            "n_subjects_attempted": len(common),
            "per_subject": per_subject,
            "shape": list(mean_fs.shape),
        })

    def validate_config(self, config: dict) -> list[str]:
        cfg = my_cfg(config, self.name)
        errors: list[str] = []
        for k in ("weights_from", "features_from"):
            if not cfg.get(k):
                errors.append(f"cross_modal_prediction.{k} is required")
        return errors
