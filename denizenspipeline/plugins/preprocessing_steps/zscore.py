"""Z-score step — z-score normalizes responses and/or features."""

from __future__ import annotations

from denizenspipeline.core.array_utils import zscore
from denizenspipeline.core.types import PreprocessingState
from denizenspipeline.plugins._decorators import preprocessing_step


@preprocessing_step("zscore")
class ZscoreStep:
    """Z-scores responses and/or features (per-run or concatenated)."""

    name = "zscore"

    def apply(self, state: PreprocessingState, params: dict) -> None:
        targets = params.get("targets", ["responses", "features"])

        if state.is_concatenated:
            # Operate on concatenated matrices
            if "responses" in targets:
                state.Y_train = zscore(state.Y_train)
                state.Y_test = zscore(state.Y_test)
            if "features" in targets:
                state.X_train = zscore(state.X_train)
                state.X_test = zscore(state.X_test)
        else:
            # Operate on per-run dicts
            if "responses" in targets:
                for run in state.all_runs:
                    if run in state.responses:
                        state.responses[run] = zscore(state.responses[run])
            if "features" in targets:
                for feat_name in state.features:
                    for run in state.all_runs:
                        if run in state.features[feat_name]:
                            state.features[feat_name][run] = zscore(
                                state.features[feat_name][run])

    def validate_params(self, params: dict) -> list[str]:
        errors = []
        targets = params.get("targets")
        if targets is not None:
            valid = {"responses", "features"}
            for t in targets:
                if t not in valid:
                    errors.append(
                        f"zscore target '{t}' invalid, must be one of {valid}")
        return errors
