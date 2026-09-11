"""Project a subject's voxel weights into a group-built subspace.

Subject-scope companion to
:class:`fmriflow.modules.group_analyzers.stacked_weights_pca.StackedWeightsPCAAnalyzer`.
Runs during the second pass of a group orchestration — the group analyzer
binds its :class:`SemanticSubspace` into each subject's context under
``external.<binding_name>``, this analyzer reads it and writes the per-voxel
K-dimensional projection back into the subject's context.
"""

from __future__ import annotations

import logging

import numpy as np

from fmriflow.core.types import ModelResult, SemanticSubspace
from fmriflow.modules._decorators import analyzer
from fmriflow.modules.analyzers._weights import slice_feature_block

logger = logging.getLogger(__name__)


@analyzer("project_to_subspace")
class ProjectToSubspaceAnalyzer:
    """Project this subject's per-voxel weights into a group subspace.

    Reads the basis from ``external.<binding_name>`` (default
    ``external.semantic_pca_basis``) and the feature-specific weight block
    from ``result``. Writes ``analysis.<output_key>`` (default
    ``analysis.semantic_pc_projection``) — a ``(n_components, n_voxels)``
    array. Downstream reporters can colour voxels by their projection
    (e.g. RGB-from-PC1-2-3 for a semantic-PC flatmap).
    """

    # Reads a value a group analyzer binds into subjects, so a minimal second pass re-runs it.
    binding_consumer = True

    name = "project_to_subspace"
    PARAM_SCHEMA = {
        "binding": {
            "type": "str",
            "default": "semantic_pca_basis",
            "description": (
                "Suffix of the 'external.*' context key holding the "
                "SemanticSubspace bound in by the group orchestrator's "
                "second-pass mechanism."
            ),
        },
        "output_key": {
            "type": "str",
            "default": "analysis.semantic_pc_projection",
            "description": (
                "Where to store the (n_components, n_voxels) projection."
            ),
        },
    }

    def analyze(self, context, config: dict) -> None:
        acfg = _my_cfg(config, self.name)
        binding = acfg.get("binding", "semantic_pca_basis")
        output_key = acfg.get("output_key", "analysis.semantic_pc_projection")

        ctx_key = f"external.{binding}"
        if not context.has(ctx_key):
            logger.warning(
                "project_to_subspace: '%s' not in context — was a group "
                "stacked_weights_pca analyzer run before this subject's "
                "second pass?", ctx_key)
            return
        basis = context.get(ctx_key, SemanticSubspace)
        result = context.get("result", ModelResult)
        block = slice_feature_block(result, basis.feature)
        if block.shape[0] != basis.basis.shape[0]:
            raise ValueError(
                f"project_to_subspace: subject weight block has "
                f"{block.shape[0]} rows but the basis expects "
                f"{basis.basis.shape[0]} (feature='{basis.feature}', "
                f"n_delays={basis.n_delays}, fdim={basis.feature_dim})"
            )
        projection = basis.basis.T @ block            # (K, n_voxels)
        context.put(output_key, projection)

    def validate_config(self, config: dict) -> list[str]:
        return []


def _my_cfg(config: dict, name: str) -> dict:
    """Pluck the project_to_subspace entry's params out of the analysis list."""
    for entry in config.get("analysis", []) or []:
        if entry.get("name") == name:
            return entry.get("params", {}) or {}
    return {}
