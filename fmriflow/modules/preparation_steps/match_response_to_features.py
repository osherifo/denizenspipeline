"""Per-run truncation step — equalize response and feature lengths.

Some datasets ship response files with variable
post-stimulus silence padding that the trim step's fixed offsets cannot
correct. This step truncates each run's response from the end (or start,
configurable) so it has the same TR count as its features.

Features are taken as ground truth because they come from the stimulus
TextGrid, which has a well-defined duration; the response file's extra TRs
are silence/HRF-decay padding that the encoding model shouldn't see.
"""
from __future__ import annotations

import logging

from fmriflow.core.types import PreparationState
from fmriflow.modules._decorators import preparation_step

logger = logging.getLogger(__name__)


@preparation_step("match_response_to_features")
class MatchResponseToFeaturesStep:
    """Truncates each run's response so its TR count equals its features'.

    params:
        from_end: bool (default True) — drop the excess TRs from the end.
            Set to False to drop them from the start instead.
        tolerate_shorter: bool (default False) — if True, runs where the
            response is *shorter* than the features are silently kept;
            otherwise the step raises a ValueError. The default is strict
            because a shorter response signals an unexpected upstream
            problem.
    """

    name = "match_response_to_features"
    PARAM_SCHEMA = {
        "from_end": {"type": "bool", "default": True, "description": "Drop excess response TRs from the end (True) or the start (False)"},
        "tolerate_shorter": {"type": "bool", "default": False, "description": "Skip runs where the response is shorter than the features"},
    }

    def apply(self, state: PreparationState, params: dict) -> None:
        from_end = bool(params.get("from_end", True))
        tolerate_shorter = bool(params.get("tolerate_shorter", False))

        # Use the first feature's TR count per run as the target length.
        if not state.features:
            logger.warning("match_response_to_features: no features loaded; skipping.")
            return
        first_feat = next(iter(state.features))

        for run in state.all_runs:
            if run not in state.responses:
                continue
            if run not in state.features[first_feat]:
                continue

            resp_n = state.responses[run].shape[0]
            feat_n = state.features[first_feat][run].shape[0]
            if resp_n == feat_n:
                continue

            if resp_n < feat_n:
                msg = (
                    f"match_response_to_features: run '{run}' response has "
                    f"{resp_n} TRs but features have {feat_n} (shorter)."
                )
                if tolerate_shorter:
                    logger.warning("%s — kept as-is.", msg)
                    continue
                raise ValueError(msg)

            excess = resp_n - feat_n
            if from_end:
                state.responses[run] = state.responses[run][:feat_n]
            else:
                state.responses[run] = state.responses[run][excess:]
            logger.info(
                "  %s response: %d -> %d (matched to features '%s', from_%s)",
                run, resp_n, feat_n, first_feat, "end" if from_end else "start",
            )

    def validate_params(self, params: dict) -> list[str]:
        errors = []
        for key in ("from_end", "tolerate_shorter"):
            v = params.get(key)
            if v is not None and not isinstance(v, bool):
                errors.append(f"{key} must be a bool, got {type(v).__name__}")
        return errors
