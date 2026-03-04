"""Split step — assigns train/test runs from config."""

from __future__ import annotations

from denizenspipeline.core.types import PreprocessingState
from denizenspipeline.plugins._decorators import preprocessing_step


@preprocessing_step("split")
class SplitStep:
    """Sets train_runs / test_runs on state from config split section."""

    name = "split"

    def apply(self, state: PreprocessingState, params: dict) -> None:
        config = params.get("_config", {})
        split_cfg = config.get("split", {})
        test_runs = split_cfg.get("test_runs", params.get("test_runs", []))

        # Determine all runs as intersection of responses and features
        response_runs = set(state.responses.keys())
        if state.features:
            first_feat = next(iter(state.features.values()))
            feature_runs = set(first_feat.keys())
            all_runs = sorted(response_runs & feature_runs)
        else:
            all_runs = sorted(response_runs)

        train_runs = params.get("train_runs") or split_cfg.get("train_runs")
        if not train_runs or train_runs == "auto":
            train_runs = sorted(set(all_runs) - set(test_runs))

        state.all_runs = all_runs
        state.train_runs = train_runs
        state.test_runs = list(test_runs)

    def validate_params(self, params: dict) -> list[str]:
        return []
