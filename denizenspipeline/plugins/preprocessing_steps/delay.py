"""Delay step — applies temporal delays to concatenated X matrices."""

from __future__ import annotations

from denizenspipeline.core.array_utils import make_delayed
from denizenspipeline.core.types import PreprocessingState
from denizenspipeline.plugins._decorators import preprocessing_step


@preprocessing_step("delay")
class DelayStep:
    """Applies temporal delays to X_train and X_test."""

    name = "delay"

    def apply(self, state: PreprocessingState, params: dict) -> None:
        delays = params.get("delays", [1, 2, 3, 4])
        state.delays = delays
        state.X_train = make_delayed(state.X_train, delays)
        state.X_test = make_delayed(state.X_test, delays)

    def validate_params(self, params: dict) -> list[str]:
        errors = []
        delays = params.get("delays")
        if delays is not None:
            if not isinstance(delays, list):
                errors.append("delays must be a list of ints")
            elif not all(isinstance(d, int) for d in delays):
                errors.append("delays must be a list of ints")
        return errors
