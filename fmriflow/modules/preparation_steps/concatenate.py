"""Concatenate step — hstacks features, vstacks runs, splits train/test."""

from __future__ import annotations

import logging

import numpy as np

from fmriflow.core.types import PreparationState
from fmriflow.modules._decorators import preparation_step

logger = logging.getLogger(__name__)


@preparation_step("concatenate")
class ConcatenateStep:
    """Horizontally stacks features, vertically stacks runs, splits train/test."""

    name = "concatenate"
    PARAM_SCHEMA = {}

    def apply(self, state: PreparationState, params: dict) -> None:
        if state.is_concatenated:
            return  # Already concatenated

        # Check row counts match between responses and features per run
        for run in state.all_runs:
            resp_rows = state.responses[run].shape[0]
            for feat_name in state.feature_names:
                feat_rows = state.features[feat_name][run].shape[0]
                if feat_rows != resp_rows:
                    raise ValueError(
                        f"Row mismatch in run '{run}': responses have "
                        f"{resp_rows} TRs but feature '{feat_name}' has "
                        f"{feat_rows}. Apply matching trim targets to both "
                        f"or use targets: [responses, features] in the "
                        f"trim step.")

        # Build per-run concatenated feature matrices
        concat_feat = {}
        for run in state.all_runs:
            run_feats = []
            for feat_name in state.feature_names:
                run_feats.append(state.features[feat_name][run])
            concat_feat[run] = np.hstack(run_feats)

        # Stack runs and split train/test
        state.Y_train = np.vstack(
            [state.responses[r] for r in state.train_runs]).astype(np.float32)
        state.Y_test = np.vstack(
            [state.responses[r] for r in state.test_runs]).astype(np.float32)
        state.X_train = np.vstack(
            [concat_feat[r] for r in state.train_runs]).astype(np.float32)
        state.X_test = np.vstack(
            [concat_feat[r] for r in state.test_runs]).astype(np.float32)

        # NaN/Inf summary
        for name, arr in [("X_train", state.X_train), ("X_test", state.X_test),
                          ("Y_train", state.Y_train), ("Y_test", state.Y_test)]:
            n_nan = int(np.isnan(arr).sum())
            n_inf = int(np.isinf(arr).sum())
            if n_nan or n_inf:
                logger.warning("After concatenate: %s has %d NaN, %d Inf (shape=%s)",
                               name, n_nan, n_inf, arr.shape)
            else:
                logger.info("After concatenate: %s shape=%s — clean", name, arr.shape)

    def validate_params(self, params: dict) -> list[str]:
        return []
