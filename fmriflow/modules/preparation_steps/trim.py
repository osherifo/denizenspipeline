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
        trim_start: int (default 5) — global trim from start
        trim_end: int (default 5) — global trim from end
        targets: list of "responses" | "features" (default both)
        per_feature: optional dict mapping feature name → ``{trim_start,
            trim_end}``. Lets one feature opt out (set both to 0) or
            use a different trim than the global. Use case:
            ``moten`` loaded from a pre-trimmed .npz needs to skip
            the global feature trim while the other features still
            get trimmed normally.
    """

    name = "trim"
    PARAM_SCHEMA = {
        "trim_start": {"type": "int", "default": 5, "min": 0, "description": "TRs to remove from start of each run"},
        "trim_end": {"type": "int", "default": 5, "min": 0, "description": "TRs to remove from end of each run"},
        "targets": {"type": "list[string]", "default": ["responses", "features"], "enum": ["responses", "features"], "description": "Which data to trim"},
        "per_feature": {"type": "dict", "description": "Per-feature trim overrides: {<feat_name>: {trim_start, trim_end}}"},
    }

    def apply(self, state: PreparationState, params: dict) -> None:
        from fmriflow import ui

        trim_start = params.get("trim_start", 5)
        trim_end = params.get("trim_end", 5)
        targets = params.get("targets", ["responses", "features"])
        per_feature: dict = params.get("per_feature") or {}

        logger.info(
            "Trim step: start=%d end=%d targets=%s per_feature=%s",
            trim_start, trim_end, targets, list(per_feature),
        )

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
                    if run not in state.features[feat_name]:
                        continue
                    f_start, f_end = self._resolve_feature_trim(
                        feat_name, per_feature, trim_start, trim_end)
                    before = state.features[feat_name][run].shape[0]
                    state.features[feat_name][run] = self._trim(
                        state.features[feat_name][run], f_start, f_end)
                    after = state.features[feat_name][run].shape[0]
                    feat_sizes[feat_name] = (before, after)
                    logger.info(
                        "  %s %s: %d -> %d (trim %d,%d)",
                        run, feat_name, before, after, f_start, f_end,
                    )
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
        per_feature = params.get("per_feature")
        if per_feature is not None:
            if not isinstance(per_feature, dict):
                errors.append("per_feature must be a dict of feature_name -> {trim_start, trim_end}")
            else:
                for feat_name, override in per_feature.items():
                    if not isinstance(override, dict):
                        errors.append(
                            f"per_feature['{feat_name}'] must be a dict with "
                            "trim_start/trim_end keys")
                        continue
                    for k in ("trim_start", "trim_end"):
                        v = override.get(k)
                        if v is not None and (not isinstance(v, int) or v < 0):
                            errors.append(
                                f"per_feature['{feat_name}'].{k} must be a "
                                f"non-negative int, got {v}")
        return errors

    @staticmethod
    def _resolve_feature_trim(
        feat_name: str, per_feature: dict, default_start: int, default_end: int,
    ) -> tuple[int, int]:
        override = per_feature.get(feat_name)
        if not isinstance(override, dict):
            return default_start, default_end
        return (
            override.get("trim_start", default_start),
            override.get("trim_end", default_end),
        )

    @staticmethod
    def _trim(arr, start, end):
        if start == 0 and end == 0:
            return arr
        if end == 0:
            return arr[start:]
        return arr[start:-end]
