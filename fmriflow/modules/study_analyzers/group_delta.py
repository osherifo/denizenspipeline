"""Voxelwise difference between two groups' artifacts.

Take each group's mean prediction-accuracy map (or any group-level
array) and compute the voxelwise A - B delta. Standard
between-modality / between-condition comparison.
Shape-compatibility validated up-front.
"""

from __future__ import annotations

import logging

import numpy as np

from fmriflow.core.study_types import StudyResult
from fmriflow.modules._decorators import study_analyzer
from fmriflow.modules.study_analyzers._helpers import my_cfg, resolve_group_key

logger = logging.getLogger(__name__)


@study_analyzer("group_delta")
class GroupDeltaAnalyzer:
    """Compute ``study[output_key] = group[a][input_key] - group[b][input_key]``.

    Both groups must produce an array of identical shape under
    ``input_key`` — typically a common-space array (fsaverage or MNI)
    so the voxelwise subtraction is meaningful. Failure to match
    shape raises ``ValueError``.
    """

    name = "group_delta"
    produces_group_artifact = False
    PARAM_SCHEMA = {
        "input_key": {
            "type": "str",
            "description": (
                "Dotted path into each GroupResult's artifacts "
                "(e.g. 'group.scores_mean')."
            ),
        },
        "a": {"type": "str", "description": "Minuend group's study-scope label."},
        "b": {"type": "str", "description": "Subtrahend group's study-scope label."},
        "output_key": {
            "type": "str",
            "description": "Study-artifact key for the resulting delta array.",
        },
    }

    def analyze(self, study: StudyResult, config: dict) -> None:
        cfg = my_cfg(config, self.name)
        input_key = cfg.get("input_key")
        label_a = cfg.get("a")
        label_b = cfg.get("b")
        output_key = cfg.get("output_key", f"study.{input_key}.delta")

        if not (input_key and label_a and label_b):
            raise ValueError(
                "group_delta requires 'input_key', 'a', and 'b' params")

        group_a = study.group(label_a)
        group_b = study.group(label_b)

        val_a = resolve_group_key(group_a, input_key)
        val_b = resolve_group_key(group_b, input_key)
        if val_a is None or val_b is None:
            missing = [
                label for label, val in [(label_a, val_a), (label_b, val_b)]
                if val is None
            ]
            raise ValueError(
                f"group_delta: '{input_key}' missing from group(s): {missing}")

        arr_a = np.asarray(val_a)
        arr_b = np.asarray(val_b)
        if arr_a.shape != arr_b.shape:
            raise ValueError(
                f"group_delta: shape mismatch for '{input_key}' — "
                f"{label_a}={arr_a.shape} vs {label_b}={arr_b.shape}. "
                "Are both groups projected to a common space?")

        delta = arr_a - arr_b
        study.put(output_key, delta)
        # Helpful provenance — readable in study_summary.html.
        study.put(f"{output_key}.meta", {
            "minuend": label_a,
            "subtrahend": label_b,
            "input_key": input_key,
            "shape": list(delta.shape),
            "dtype": str(delta.dtype),
        })

    def validate_config(self, config: dict) -> list[str]:
        cfg = my_cfg(config, self.name)
        errors: list[str] = []
        for k in ("input_key", "a", "b"):
            if not cfg.get(k):
                errors.append(f"group_delta.{k} is required")
        return errors
