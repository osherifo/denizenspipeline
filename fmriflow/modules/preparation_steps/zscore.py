"""Z-score step — z-score normalizes responses and/or features."""

from __future__ import annotations

import logging

import numpy as np

from fmriflow.core.array_utils import zscore
from fmriflow.core.types import PreparationState
from fmriflow.modules._decorators import preparation_step

logger = logging.getLogger(__name__)


def _nan_report(arr: np.ndarray, label: str) -> None:
    """Log a warning if arr contains NaN or Inf."""
    n_nan = int(np.isnan(arr).sum())
    n_inf = int(np.isinf(arr).sum())
    if n_nan or n_inf:
        logger.warning("NaN/Inf after zscore in %s: %d NaN, %d Inf (shape=%s)",
                       label, n_nan, n_inf, arr.shape)


@preparation_step("zscore")
class ZscoreStep:
    """Z-scores responses and/or features (per-run or concatenated)."""

    name = "zscore"
    PARAM_SCHEMA = {
        "targets": {"type": "list[string]", "default": ["responses", "features"], "enum": ["responses", "features"], "description": "Which data to z-score"},
    }

    def apply(self, state: PreparationState, params: dict) -> None:
        targets = params.get("targets", ["responses", "features"])

        if state.is_concatenated:
            # Operate on concatenated matrices
            if "responses" in targets:
                state.Y_train = zscore(state.Y_train)
                state.Y_test = zscore(state.Y_test)
                _nan_report(state.Y_train, "Y_train")
                _nan_report(state.Y_test, "Y_test")
            if "features" in targets:
                state.X_train = zscore(state.X_train)
                state.X_test = zscore(state.X_test)
                _nan_report(state.X_train, "X_train")
                _nan_report(state.X_test, "X_test")
        else:
            # Operate on per-run dicts
            if "responses" in targets:
                for run in state.all_runs:
                    if run in state.responses:
                        state.responses[run] = zscore(state.responses[run])
                        _nan_report(state.responses[run], f"responses/{run}")
            if "features" in targets:
                for feat_name in state.features:
                    for run in state.all_runs:
                        if run in state.features[feat_name]:
                            state.features[feat_name][run] = zscore(
                                state.features[feat_name][run])
                            _nan_report(state.features[feat_name][run],
                                        f"features/{feat_name}/{run}")

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
