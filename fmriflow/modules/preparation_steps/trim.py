"""Trim step — removes start/end TRs from per-run data."""

from __future__ import annotations

import logging

from fmriflow.core.types import PreparationState
from fmriflow.modules._decorators import preparation_step

logger = logging.getLogger(__name__)


@preparation_step("trim")
class TrimStep:
    """Trims start/end TRs from responses and/or features (per-run).

    params:
        trim_start: int (default 5)
        trim_end: int (default 5)
        targets: list of "responses" | "features" (default both)
    """

    name = "trim"
    PARAM_SCHEMA = {
        "trim_start": {"type": "int", "default": 5, "min": 0, "description": "TRs to remove from start of each run"},
        "trim_end": {"type": "int", "default": 5, "min": 0, "description": "TRs to remove from end of each run"},
        "targets": {"type": "list[string]", "default": ["responses", "features"], "enum": ["responses", "features"], "description": "Which data to trim"},
    }

    def apply(self, state: PreparationState, params: dict) -> None:
        from fmriflow import ui

        trim_start = params.get("trim_start", 5)
        trim_end = params.get("trim_end", 5)
        targets = params.get("targets", ["responses", "features"])

        logger.info("Trim step: start=%d end=%d targets=%s", trim_start, trim_end, targets)

        if "responses" in targets:
            run_shapes = []
            for run in state.all_runs:
                if run in state.responses:
                    before = state.responses[run].shape[0]
                    state.responses[run] = self._trim(
                        state.responses[run], trim_start, trim_end)
                    after = state.responses[run].shape[0]
                    run_shapes.append((run, before, after))
                    logger.info("  %s responses: %d -> %d", run, before, after)
            ui.trim_table("responses", trim_start, trim_end, run_shapes)

        if "features" in targets:
            run_shapes = []
            for run in state.all_runs:
                feat_sizes = {}
                for feat_name in state.features:
                    if run in state.features[feat_name]:
                        before = state.features[feat_name][run].shape[0]
                        state.features[feat_name][run] = self._trim(
                            state.features[feat_name][run], trim_start, trim_end)
                        after = state.features[feat_name][run].shape[0]
                        feat_sizes[feat_name] = (before, after)
                        logger.info("  %s %s: %d -> %d", run, feat_name, before, after)
                if feat_sizes:
                    first_before, first_after = next(iter(feat_sizes.values()))
                    mismatches = [
                        f"{fn}:{sz[1]}"
                        for fn, sz in feat_sizes.items()
                        if sz[1] != first_after
                    ]
                    label = run
                    if mismatches:
                        label = f"{run}  [bold yellow]({', '.join(mismatches)} differ!)[/]"
                    run_shapes.append((label, first_before, first_after))
            ui.trim_table("features", trim_start, trim_end, run_shapes)

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
