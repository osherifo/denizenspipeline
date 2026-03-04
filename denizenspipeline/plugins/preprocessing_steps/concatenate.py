"""Concatenate step — hstacks features, vstacks runs, splits train/test."""

from __future__ import annotations

import numpy as np

from denizenspipeline.core.types import PreprocessingState
from denizenspipeline.plugins._decorators import preprocessing_step


@preprocessing_step("concatenate")
class ConcatenateStep:
    """Horizontally stacks features, vertically stacks runs, splits train/test."""

    name = "concatenate"

    def apply(self, state: PreprocessingState, params: dict) -> None:
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
            [state.responses[r] for r in state.train_runs])
        state.Y_test = np.vstack(
            [state.responses[r] for r in state.test_runs])
        state.X_train = np.vstack(
            [concat_feat[r] for r in state.train_runs])
        state.X_test = np.vstack(
            [concat_feat[r] for r in state.test_runs])

    def validate_params(self, params: dict) -> list[str]:
        return []
