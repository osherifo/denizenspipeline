"""SemanticPCCorrelation — Deniz 2019 Fig 5.

For each subject present in both groups, the per-modality
:class:`SemanticSubspace` projection ``analysis.semantic_pc_projection``
(``K x n_voxels``) was planted by the subject-scope
``project_to_subspace`` analyzer during each group's second pass.

This study analyzer:

1. picks the top-K best-predicted voxels per subject (mean of the two
   modalities' within-modality prediction accuracy);
2. correlates the two modalities' PC projections restricted to those
   voxels, per PC;
3. stacks the result into a ``(n_subjects, n_components)`` array.

The companion reporter ``study_pc_correlation_bar`` renders it as the
paper's Fig 5 per-PC scatter + bar.
"""

from __future__ import annotations

import logging

import numpy as np

from fmriflow.core.study_types import StudyResult
from fmriflow.core.types import ModelResult
from fmriflow.modules._decorators import study_analyzer
from fmriflow.modules.study_analyzers._cross_modal import (
    best_predicted_voxels, common_subjects, pearson_per_voxel,
)
from fmriflow.modules.study_analyzers._helpers import my_cfg

logger = logging.getLogger(__name__)


@study_analyzer("semantic_pc_correlation")
class SemanticPCCorrelationAnalyzer:
    """Per-subject per-PC correlation of semantic projections across modalities."""

    name = "semantic_pc_correlation"
    produces_group_artifact = False
    PARAM_SCHEMA = {
        "a": {"type": "str", "description": "First group label."},
        "b": {"type": "str", "description": "Second group label."},
        "projection_key": {
            "type": "str",
            "default": "analysis.semantic_pc_projection",
            "description": (
                "Subject-context key holding the (K, n_voxels) PC "
                "projection planted by the second-pass "
                "project_to_subspace analyzer."
            ),
        },
        "top_k_voxels": {
            "type": "int",
            "default": 10000,
            "description": (
                "How many best-predicted voxels (by mean accuracy "
                "across the two modalities) to keep for the per-PC "
                "correlation. Mirrors Deniz 2019's 10,000-voxel restriction."
            ),
        },
        "n_components": {
            "type": "int",
            "description": (
                "Cap on how many PCs to correlate. Defaults to all PCs "
                "in the projection."
            ),
        },
        "output_key": {
            "type": "str",
            "default": "study.semantic_pc_correlation",
            "description": (
                "Study-artifact key for the (n_subjects, n_components) "
                "correlation matrix."
            ),
        },
    }

    def analyze(self, study: StudyResult, config: dict) -> None:
        cfg = my_cfg(config, self.name)
        label_a = cfg.get("a")
        label_b = cfg.get("b")
        if not (label_a and label_b):
            raise ValueError("semantic_pc_correlation: 'a' and 'b' required")
        projection_key = cfg.get(
            "projection_key", "analysis.semantic_pc_projection")
        top_k = int(cfg.get("top_k_voxels", 10000))
        n_components_cap = cfg.get("n_components")
        output_key = cfg.get("output_key", "study.semantic_pc_correlation")

        group_a = study.group(label_a)
        group_b = study.group(label_b)
        a_by, b_by, common = common_subjects(group_a, group_b)
        if not common:
            raise ValueError(
                f"semantic_pc_correlation: no shared subjects between "
                f"'{label_a}' and '{label_b}'")

        kept_subjects: list[str] = []
        rows: list[np.ndarray] = []

        for sub in common:
            sa, sb = a_by[sub], b_by[sub]
            ctx_a, ctx_b = sa.context, sb.context
            if not (ctx_a.has(projection_key) and ctx_b.has(projection_key)):
                logger.warning(
                    "semantic_pc_correlation: subject %s missing '%s' in "
                    "one modality — skipping (was the second-pass "
                    "project_to_subspace run?)", sub, projection_key)
                continue
            proj_a = np.asarray(ctx_a.get(projection_key))      # (K, n_vox)
            proj_b = np.asarray(ctx_b.get(projection_key))      # (K, n_vox)
            if proj_a.shape != proj_b.shape:
                logger.warning(
                    "semantic_pc_correlation: subject %s projection shape "
                    "mismatch %s vs %s — skipping",
                    sub, proj_a.shape, proj_b.shape)
                continue
            if not (ctx_a.has("result") and ctx_b.has("result")):
                logger.warning(
                    "semantic_pc_correlation: subject %s missing 'result' "
                    "in one modality — skipping", sub)
                continue
            r_a = ctx_a.get("result", ModelResult)
            r_b = ctx_b.get("result", ModelResult)
            try:
                vox_idx = best_predicted_voxels(r_a, r_b, top_k)
            except ValueError as exc:
                logger.warning(
                    "semantic_pc_correlation: %s — skipping subject %s",
                    exc, sub)
                continue

            # Restrict each projection to the best-predicted voxels,
            # then correlate per PC. ``pearson_per_voxel`` treats the
            # first axis as samples, the second as variables — so
            # transpose to (n_vox_top, K) before calling.
            a_sub = proj_a[:, vox_idx].T                        # (top_k, K)
            b_sub = proj_b[:, vox_idx].T                        # (top_k, K)
            per_pc = pearson_per_voxel(a_sub, b_sub)            # (K,)
            if n_components_cap is not None:
                per_pc = per_pc[: int(n_components_cap)]
            rows.append(per_pc)
            kept_subjects.append(sub)

        if not rows:
            logger.warning(
                "semantic_pc_correlation: no subjects produced a per-PC "
                "correlation — leaving '%s' unset", output_key)
            return

        matrix = np.stack(rows, axis=0)                  # (n_subj, K)
        study.put(output_key, matrix)
        study.put(f"{output_key}.meta", {
            "a": label_a, "b": label_b,
            "projection_key": projection_key,
            "top_k_voxels": top_k,
            "n_components": int(matrix.shape[1]),
            "subjects": kept_subjects,
            "shape": list(matrix.shape),
        })

    def validate_config(self, config: dict) -> list[str]:
        cfg = my_cfg(config, self.name)
        errors: list[str] = []
        for k in ("a", "b"):
            if not cfg.get(k):
                errors.append(f"semantic_pc_correlation.{k} is required")
        return errors
