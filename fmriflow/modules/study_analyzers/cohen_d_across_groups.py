"""Voxelwise Cohen's d effect size between two groups.

Reads each subject's in-memory context under ``input_key`` (so the
groups must have been run inside this study invocation — disk-only
group runs from a previous study don't expose subject contexts).
Computes ``(mean_a - mean_b) / pooled_std`` voxelwise.

Pairs well with subject-level fsaverage-projected accuracy maps:
``input_key: analysis.fsaverage_scores`` gives a common-space d-map
that compares the per-subject distributions head-to-head.
"""

from __future__ import annotations

import logging

import numpy as np

from fmriflow.core.study_types import StudyResult
from fmriflow.modules._decorators import study_analyzer
from fmriflow.modules.group_analyzers._helpers import resolve_subject_key
from fmriflow.modules.study_analyzers._helpers import my_cfg

logger = logging.getLogger(__name__)


@study_analyzer("cohen_d_across_groups")
class CohenDAcrossGroupsAnalyzer:
    """Voxelwise Cohen's d between two groups' per-subject arrays.

    ``d = (mean_a - mean_b) / pooled_std``, where the pooled standard
    deviation uses sample variance (``ddof=1``). Returns a NaN at any
    voxel where pooled_std is zero (degenerate — every subject in
    both groups has the same value).
    """

    name = "cohen_d_across_groups"
    produces_group_artifact = False
    PARAM_SCHEMA = {
        "input_key": {
            "type": "str",
            "description": (
                "Dotted path into each subject's PipelineContext "
                "(e.g. 'analysis.fsaverage_scores')."
            ),
        },
        "a": {"type": "str", "description": "Group A's study-scope label."},
        "b": {"type": "str", "description": "Group B's study-scope label."},
        "output_key": {
            "type": "str",
            "description": "Study-artifact key for the resulting d-map.",
        },
    }

    def analyze(self, study: StudyResult, config: dict) -> None:
        cfg = my_cfg(config, self.name)
        input_key = cfg.get("input_key")
        label_a = cfg.get("a")
        label_b = cfg.get("b")
        output_key = cfg.get("output_key", f"study.{input_key}.cohen_d")

        if not (input_key and label_a and label_b):
            raise ValueError(
                "cohen_d_across_groups requires 'input_key', 'a', and 'b'")

        arr_a = _stack_subjects(study.group(label_a), input_key, label_a)
        arr_b = _stack_subjects(study.group(label_b), input_key, label_b)
        if arr_a.shape[1:] != arr_b.shape[1:]:
            raise ValueError(
                f"cohen_d_across_groups: shape mismatch beyond subject axis "
                f"— {label_a}={arr_a.shape} vs {label_b}={arr_b.shape}")

        mean_a = arr_a.mean(axis=0)
        mean_b = arr_b.mean(axis=0)
        var_a = arr_a.var(axis=0, ddof=1) if arr_a.shape[0] > 1 else np.zeros_like(mean_a)
        var_b = arr_b.var(axis=0, ddof=1) if arr_b.shape[0] > 1 else np.zeros_like(mean_b)
        n_a = arr_a.shape[0]
        n_b = arr_b.shape[0]
        pooled = np.sqrt(((n_a - 1) * var_a + (n_b - 1) * var_b)
                         / max(1, (n_a + n_b - 2)))
        with np.errstate(divide="ignore", invalid="ignore"):
            d = np.where(pooled > 0, (mean_a - mean_b) / pooled, np.nan)

        study.put(output_key, d)
        study.put(f"{output_key}.meta", {
            "a": label_a,
            "b": label_b,
            "input_key": input_key,
            "n_a": n_a,
            "n_b": n_b,
            "shape": list(d.shape),
            "dtype": str(d.dtype),
        })

    def validate_config(self, config: dict) -> list[str]:
        cfg = my_cfg(config, self.name)
        errors: list[str] = []
        for k in ("input_key", "a", "b"):
            if not cfg.get(k):
                errors.append(f"cohen_d_across_groups.{k} is required")
        return errors


def _stack_subjects(group, key: str, label: str) -> np.ndarray:
    """Stack each subject's ``key`` into a ``(n_subjects, *voxel_shape)`` array.

    Subjects missing the key (e.g. context was dropped on resume) are
    warned about and skipped; raises if no subject contributed.
    """
    rows: list[np.ndarray] = []
    skipped: list[str] = []
    for sr in group.subjects:
        value = resolve_subject_key(sr.context, key)
        if value is None:
            skipped.append(sr.subject)
            continue
        rows.append(np.asarray(value))
    if skipped:
        logger.warning(
            "cohen_d_across_groups: group '%s' — %d/%d subject(s) missing "
            "'%s' (context dropped on resume?)",
            label, len(skipped), len(group.subjects), key)
    if not rows:
        raise ValueError(
            f"cohen_d_across_groups: no subjects in group '{label}' "
            f"produced key '{key}'")
    return np.stack(rows, axis=0)
