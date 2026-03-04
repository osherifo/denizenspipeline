"""Trim step — removes start/end TRs from per-run data."""

from __future__ import annotations

from denizenspipeline.core.types import PreprocessingState
from denizenspipeline.plugins._decorators import preprocessing_step


@preprocessing_step("trim")
class TrimStep:
    """Trims start/end TRs from responses and/or features (per-run).

    params:
        trim_start: int (default 5)
        trim_end: int (default 5)
        targets: list of "responses" | "features" (default both)
    """

    name = "trim"

    def apply(self, state: PreprocessingState, params: dict) -> None:
        trim_start = params.get("trim_start", 5)
        trim_end = params.get("trim_end", 5)
        targets = params.get("targets", ["responses", "features"])

        for run in state.all_runs:
            if "responses" in targets and run in state.responses:
                state.responses[run] = self._trim(
                    state.responses[run], trim_start, trim_end)
            if "features" in targets:
                for feat_name in state.features:
                    if run in state.features[feat_name]:
                        state.features[feat_name][run] = self._trim(
                            state.features[feat_name][run], trim_start, trim_end)

    def validate_params(self, params: dict) -> list[str]:
        errors = []
        for key in ("trim_start", "trim_end"):
            val = params.get(key)
            if val is not None and (not isinstance(val, int) or val < 0):
                errors.append(f"{key} must be a non-negative int, got {val}")
        targets = params.get("targets")
        if targets is not None:
            valid = {"responses", "features"}
            for t in targets:
                if t not in valid:
                    errors.append(
                        f"trim target '{t}' invalid, must be one of {valid}")
        return errors

    @staticmethod
    def _trim(arr, start, end):
        if end == 0:
            return arr[start:]
        return arr[start:-end]
