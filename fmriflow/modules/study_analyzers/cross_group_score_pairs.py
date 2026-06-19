"""CrossGroupScorePairs — pair each subject's within-modality voxel
scores from two groups.

For every subject present in both groups (cross-section), pull a
per-voxel score array from each group's subject context and store
the pair as a study artifact. Per-subject native-space arrays — no
fsaverage projection — because the companion density-plot reporter
visualises voxels in the subject's own brain (each subject keeps its
own mask, voxel count, and noise floor).

The default ``input_key`` is ``result.scores`` (the
:class:`ModelResult.scores` per-voxel Pearson r), but any subject-
context key whose value is a 1-D per-voxel array works — e.g.
``analysis.fsaverage_scores`` for a common-space variant.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from fmriflow.core.study_types import StudyResult
from fmriflow.modules._decorators import study_analyzer
from fmriflow.modules.group_analyzers._helpers import resolve_subject_key
from fmriflow.modules.study_analyzers._cross_modal import common_subjects
from fmriflow.modules.study_analyzers._helpers import my_cfg

logger = logging.getLogger(__name__)


@study_analyzer("cross_group_score_pairs")
class CrossGroupScorePairsAnalyzer:
    """Pair each subject's per-voxel scores across two groups."""

    name = "cross_group_score_pairs"
    produces_group_artifact = False
    PARAM_SCHEMA = {
        "a": {
            "type": "str",
            "description": "Study-scope label of the group plotted on the x-axis.",
        },
        "b": {
            "type": "str",
            "description": "Study-scope label of the group plotted on the y-axis.",
        },
        "input_key": {
            "type": "str",
            "default": "result.scores",
            "description": (
                "Dotted key resolved against each subject's PipelineContext. "
                "Defaults to ``result.scores`` — the model's per-voxel "
                "prediction-accuracy array."
            ),
        },
        "output_key": {
            "type": "str",
            "default": "study.score_pairs",
            "description": (
                "Study-artifact key. The value is a dict "
                "{subject: {'a': array, 'b': array}}; companion meta is "
                "stored at <output_key>.meta."
            ),
        },
    }

    def analyze(self, study: StudyResult, config: dict) -> None:
        cfg = my_cfg(config, self.name)
        label_a = cfg.get("a")
        label_b = cfg.get("b")
        if not (label_a and label_b):
            raise ValueError(
                "cross_group_score_pairs: 'a' and 'b' are required")
        if label_a == label_b:
            raise ValueError(
                "cross_group_score_pairs: 'a' and 'b' must be different "
                "groups")
        input_key = cfg.get("input_key", "result.scores")
        output_key = cfg.get("output_key", "study.score_pairs")

        group_a = study.group(label_a)
        group_b = study.group(label_b)
        a_by, b_by, common = common_subjects(group_a, group_b)
        if not common:
            raise ValueError(
                f"cross_group_score_pairs: no shared subjects between "
                f"'{label_a}' and '{label_b}'")

        pairs: dict[str, dict[str, Any]] = {}
        kept: list[str] = []
        for sub in common:
            arr_a = _resolve_array(a_by[sub], input_key, label_a, sub)
            arr_b = _resolve_array(b_by[sub], input_key, label_b, sub)
            if arr_a is None or arr_b is None:
                continue
            if arr_a.shape != arr_b.shape:
                logger.warning(
                    "cross_group_score_pairs: subject %s shape mismatch "
                    "%s vs %s — skipping", sub, arr_a.shape, arr_b.shape)
                continue
            pairs[sub] = {
                "a": arr_a.astype(np.float32, copy=False),
                "b": arr_b.astype(np.float32, copy=False),
                "n_voxels": int(arr_a.size),
            }
            kept.append(sub)

        if not pairs:
            raise ValueError(
                "cross_group_score_pairs: no subjects produced paired "
                "scores (missing context or shape mismatches across all)")

        study.put(output_key, pairs)
        study.put(f"{output_key}.meta", {
            "a_group": label_a,
            "b_group": label_b,
            "input_key": input_key,
            "subjects": kept,
        })

    def validate_config(self, config: dict) -> list[str]:
        cfg = my_cfg(config, self.name)
        errors: list[str] = []
        if not cfg.get("a"):
            errors.append("cross_group_score_pairs.a is required")
        if not cfg.get("b"):
            errors.append("cross_group_score_pairs.b is required")
        if cfg.get("a") and cfg.get("a") == cfg.get("b"):
            errors.append("cross_group_score_pairs: 'a' and 'b' must differ")
        return errors


def _resolve_array(sr, key: str, label: str, sub: str) -> np.ndarray | None:
    val = resolve_subject_key(sr.context, key)
    if val is None:
        logger.warning(
            "cross_group_score_pairs: subject %s in '%s' has no '%s' "
            "in context — skipping", sub, label, key)
        return None
    arr = np.asarray(val)
    # Validate the real dimensionality *before* flattening — ravel() would
    # make ndim==1 unconditionally and silently accept 2-D/3-D inputs.
    # squeeze() tolerates trivial axes like (1, V)/(V, 1) but rejects a
    # genuine multi-dim array (e.g. a (V, n_dims) tuning matrix).
    squeezed = np.squeeze(arr)
    if squeezed.ndim != 1 or squeezed.size == 0:
        logger.warning(
            "cross_group_score_pairs: subject %s '%s' has shape %s — not a "
            "1-D per-voxel array, skipping", sub, key, arr.shape)
        return None
    return squeezed
