"""Cross-subject PCA of stacked weight matrices.

For one named feature, concatenate every subject's weight block along
the voxel axis and run SVD to build a shared K-dimensional basis. Each
subject's voxels can then be projected into that basis by the subject-scope
:class:`fmriflow.modules.analyzers.project_to_subspace.ProjectToSubspaceAnalyzer`
during the orchestrator's second pass.

This is the "build a shared semantic subspace from the cohort" path —
contrast with :mod:`external_pca_basis` which loads a pre-existing
basis instead.
"""

from __future__ import annotations

import logging

import numpy as np

from fmriflow.core.group_types import GroupResult
from fmriflow.core.types import ModelResult, SemanticSubspace
from fmriflow.modules._decorators import group_analyzer
from fmriflow.modules.analyzers._weights import slice_feature_block
from fmriflow.modules.group_analyzers._helpers import my_cfg

logger = logging.getLogger(__name__)


@group_analyzer("stacked_weights_pca")
class StackedWeightsPCAAnalyzer:
    """Build a shared :class:`SemanticSubspace` from N subjects' weights.

    Triggers the orchestrator's second-pass mechanism via
    ``produces_subject_artifact = True`` — after the analyzer runs, every
    subject's ``analyze + report`` stages re-run with the resulting basis
    bound into context under ``external.semantic_pca_basis``.
    """

    name = "stacked_weights_pca"
    produces_subject_artifact = True
    PARAM_SCHEMA = {
        "feature": {
            "type": "str",
            "required": True,
            "description": (
                "Name of the feature whose delayed-weight block to stack "
                "and decompose. Must be one of the subject's "
                "ModelResult.feature_names."
            ),
        },
        "n_components": {
            "type": "int",
            "default": 50,
            "description": "Number of leading components to keep.",
        },
        "output_key": {
            "type": "str",
            "description": (
                "Group artifact key. Defaults to "
                "'group.<feature>_pca_basis'."
            ),
        },
        "binding_name": {
            "type": "str",
            "description": (
                "Bare name (no 'external.' prefix) under which the "
                "basis is bound into each subject's context during the "
                "second pass. Defaults to '<feature>_pca_basis'."
            ),
        },
    }

    def analyze(self, group: GroupResult, config: dict) -> None:
        cfg = my_cfg(config, self.name)
        feature = cfg.get("feature")
        if not feature:
            raise ValueError("stacked_weights_pca: 'feature' is required")
        n_components = int(cfg.get("n_components", 50))
        output_key = cfg.get("output_key", f"group.{feature}_pca_basis")

        blocks: list[np.ndarray] = []
        first_meta: tuple[int, int] | None = None     # (n_rows, fdim)
        contributing: list[str] = []

        for sr in group.subjects:
            if sr.context is None:
                logger.warning(
                    "stacked_weights_pca: subject %s has no in-memory "
                    "context — skipping", sr.subject)
                continue
            if not sr.context.has("result"):
                logger.warning(
                    "stacked_weights_pca: subject %s has no 'result' in "
                    "context — skipping", sr.subject)
                continue
            result = sr.context.get("result", ModelResult)
            try:
                block = slice_feature_block(result, feature)
            except KeyError as e:
                raise ValueError(
                    f"stacked_weights_pca: subject {sr.subject}: {e}"
                ) from None
            fdim = int(result.feature_dims[result.feature_names.index(feature)])
            if first_meta is None:
                first_meta = (block.shape[0], fdim)
            elif block.shape[0] != first_meta[0]:
                raise ValueError(
                    f"stacked_weights_pca: subject {sr.subject} feature "
                    f"'{feature}' has {block.shape[0]} delayed rows; "
                    f"expected {first_meta[0]}"
                )
            blocks.append(block.astype(np.float64))
            contributing.append(sr.subject)

        if not blocks:
            raise ValueError(
                f"stacked_weights_pca: no subjects produced weights for "
                f"feature '{feature}'")

        stacked = np.concatenate(blocks, axis=1)        # (n_rows, sum_voxels)
        n_rows, fdim = first_meta
        k = min(n_components, min(stacked.shape))
        # u: (n_rows, k) — the basis in feature-weight space.
        # s: (k,)
        u, s, _vt = np.linalg.svd(stacked, full_matrices=False)
        basis = u[:, :k]
        singular = s[:k]
        n_delays = max(1, n_rows // max(1, fdim))

        subspace = SemanticSubspace(
            basis=basis,
            singular_values=singular,
            feature=feature,
            n_delays=n_delays,
            feature_dim=fdim,
            metadata={
                "subjects": contributing,
                "n_voxels_total": int(stacked.shape[1]),
            },
        )
        group.put(output_key, subspace)
        # Record where the binding will land so the HTML reporter and the
        # subject-scope analyzer agree on the name.
        binding_name = cfg.get("binding_name", f"{feature}_pca_basis")
        group.put(f"{output_key}.binding_name", binding_name)

    def subject_bindings(self, group: GroupResult) -> dict[str, object]:
        # Bind every PCA basis this analyzer produced into each subject's
        # context. Cooperates with multiple PCA analyzers in one config.
        bindings: dict[str, object] = {}
        for key, value in group.artifacts.items():
            if not isinstance(value, SemanticSubspace):
                continue
            binding_name_key = f"{key}.binding_name"
            name = group.artifacts.get(binding_name_key,
                                       f"{value.feature}_pca_basis")
            bindings[name] = value
        return bindings

    def validate_config(self, config: dict) -> list[str]:
        cfg = my_cfg(config, self.name)
        if not cfg.get("feature"):
            return ["stacked_weights_pca: 'feature' param is required"]
        n = cfg.get("n_components", 50)
        if not isinstance(n, int) or n <= 0:
            return ["stacked_weights_pca: 'n_components' must be a positive int"]
        return []
