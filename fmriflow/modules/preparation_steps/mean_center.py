"""Mean-center step — mean-centers without dividing by std."""

from __future__ import annotations

from fmriflow.core.array_utils import mean_center
from fmriflow.core.types import PreparationState
from fmriflow.modules._decorators import preparation_step


@preparation_step("mean_center")
class MeanCenterStep:
    """Mean-centers responses and/or features (per-run or concatenated)."""

    name = "mean_center"
    PARAM_SCHEMA = {
        "targets": {"type": "list[string]", "default": ["responses", "features"], "enum": ["responses", "features"], "description": "Which data to mean-center"},
    }

    def apply(self, state: PreparationState, params: dict) -> None:
        targets = params.get("targets", ["responses", "features"])

        if state.is_concatenated:
            if "responses" in targets:
                state.Y_train, _ = mean_center(state.Y_train)
                state.Y_test, _ = mean_center(state.Y_test)
            if "features" in targets:
                state.X_train, _ = mean_center(state.X_train)
                state.X_test, _ = mean_center(state.X_test)
        else:
            if "responses" in targets:
                for run in state.all_runs:
                    if run in state.responses:
                        state.responses[run], _ = mean_center(
                            state.responses[run])
            if "features" in targets:
                for feat_name in state.features:
                    for run in state.all_runs:
                        if run in state.features[feat_name]:
                            state.features[feat_name][run], _ = mean_center(
                                state.features[feat_name][run])

    def validate_params(self, params: dict) -> list[str]:
        errors = []
        targets = params.get("targets")
        if targets is not None:
            valid = {"responses", "features"}
            for t in targets:
                if t not in valid:
                    errors.append(
                        f"mean_center target '{t}' invalid, "
                        f"must be one of {valid}")
        return errors
