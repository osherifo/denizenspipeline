"""CrossWithinSummary — Deniz 2019 Fig 9.

Combines the within-modality and cross-modality prediction-accuracy
maps the rest of the study layer already produces:

* within-modality summary per voxel = ``max(group.fsaverage_scores_mean
  for group in within_groups)``
* cross-modality summary per voxel = ``mean(study.<key> for key in
  cross_keys)`` (typically the two ``cross_modal_prediction`` outputs)

The two arrays are stacked into a ``(n_vertices, 2)`` study artifact
that the companion ``study_cross_within_flatmap`` reporter renders as
the paper's two-tone summary (well-predicted within only = orange,
well-predicted both = white).
"""

from __future__ import annotations

import logging

import numpy as np

from fmriflow.core.study_types import StudyResult
from fmriflow.modules._decorators import study_analyzer
from fmriflow.modules.study_analyzers._helpers import (
    my_cfg, resolve_group_key,
)

logger = logging.getLogger(__name__)


@study_analyzer("cross_within_summary")
class CrossWithinSummaryAnalyzer:
    """Pair within-vs-cross prediction accuracy per fsaverage vertex."""

    name = "cross_within_summary"
    produces_group_artifact = False
    PARAM_SCHEMA = {
        "within_groups": {
            "type": "list[str]",
            "description": (
                "Study-scope group labels whose group-mean fsaverage "
                "prediction accuracy (group.fsaverage_scores_mean) "
                "to take the per-vertex max of."
            ),
        },
        "within_key": {
            "type": "str",
            "default": "group.fsaverage_scores_mean",
            "description": (
                "Key inside each within-group artifact dict. Override "
                "to pair with a different summary metric."
            ),
        },
        "cross_keys": {
            "type": "list[str]",
            "description": (
                "Study-artifact keys whose values to per-vertex-average. "
                "Typically the two cross_modal_prediction outputs."
            ),
        },
        "output_key": {
            "type": "str",
            "default": "study.cross_within_summary",
            "description": (
                "Study-artifact key for the (n_vertices, 2) stacked "
                "array — column 0 is within-modality max, column 1 "
                "is cross-modality mean."
            ),
        },
    }

    def analyze(self, study: StudyResult, config: dict) -> None:
        cfg = my_cfg(config, self.name)
        within_groups = cfg.get("within_groups") or []
        cross_keys = cfg.get("cross_keys") or []
        within_key = cfg.get("within_key", "group.fsaverage_scores_mean")
        output_key = cfg.get("output_key", "study.cross_within_summary")

        if not within_groups:
            raise ValueError(
                "cross_within_summary: 'within_groups' is required")
        if not cross_keys:
            raise ValueError(
                "cross_within_summary: 'cross_keys' is required")

        within_arrays: list[np.ndarray] = []
        for label in within_groups:
            group = study.group(label)
            val = resolve_group_key(group, within_key)
            if val is None:
                raise ValueError(
                    f"cross_within_summary: group '{label}' has no "
                    f"'{within_key}'")
            within_arrays.append(np.asarray(val))
        within_stack = np.stack(within_arrays, axis=0)
        within_max = np.nanmax(within_stack, axis=0)

        cross_arrays: list[np.ndarray] = []
        for key in cross_keys:
            if not study.has(key):
                raise ValueError(
                    f"cross_within_summary: study has no '{key}' — "
                    "did cross_modal_prediction run with this output_key?")
            cross_arrays.append(np.asarray(study.get(key)))
        cross_stack = np.stack(cross_arrays, axis=0)
        cross_mean = np.nanmean(cross_stack, axis=0)

        if within_max.shape != cross_mean.shape:
            raise ValueError(
                f"cross_within_summary: shape mismatch "
                f"within={within_max.shape} vs cross={cross_mean.shape} "
                "— are both in fsaverage space?")

        summary = np.stack([within_max, cross_mean], axis=1)   # (n_verts, 2)
        study.put(output_key, summary)
        study.put(f"{output_key}.meta", {
            "within_groups": list(within_groups),
            "within_key": within_key,
            "cross_keys": list(cross_keys),
            "shape": list(summary.shape),
        })

    def validate_config(self, config: dict) -> list[str]:
        cfg = my_cfg(config, self.name)
        errors: list[str] = []
        if not cfg.get("within_groups"):
            errors.append("cross_within_summary.within_groups is required")
        if not cfg.get("cross_keys"):
            errors.append("cross_within_summary.cross_keys is required")
        return errors
