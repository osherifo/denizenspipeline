"""Voxelwise mean and SEM across subjects.

Reads a per-subject array from a configurable context key, stacks them,
and writes the voxelwise mean and SEM to the group result. Assumes the
arrays are already in a common space — every subject must produce an
array of identical shape.
"""

from __future__ import annotations

import logging

import numpy as np

from fmriflow.core.group_types import GroupResult
from fmriflow.modules._decorators import group_analyzer
from fmriflow.modules.group_analyzers._helpers import my_cfg, resolve_subject_key

logger = logging.getLogger(__name__)


@group_analyzer("voxelwise_mean")
class VoxelwiseMeanAnalyzer:
    """Per-voxel mean (and SEM) of a subject-level array across the group.

    Writes ``group.<output_key>`` (mean), ``group.<output_key>.sem`` (standard
    error of the mean), and ``group.<output_key>.n_subjects`` (count of
    contributing subjects) to the :class:`GroupResult`.

    Defaults to averaging ``result.scores`` from each subject, which is the
    voxelwise correlation metric used by every model in the registry.
    """

    name = "voxelwise_mean"
    produces_subject_artifact = False
    PARAM_SCHEMA = {
        "input_key": {
            "type": "str",
            "default": "result.scores",
            "description": (
                "Dotted path into each subject's PipelineContext. Example: "
                "'result.scores' for voxelwise model accuracy, or "
                "'analysis.semantic_pc_projection' for an analyzer output."
            ),
        },
        "output_key": {
            "type": "str",
            "description": (
                "Group-artifact key for the mean. SEM and n_subjects are "
                "stored at '<output_key>.sem' / '<output_key>.n_subjects'. "
                "Defaults to 'group.<input_key>.mean'."
            ),
        },
    }

    def analyze(self, group: GroupResult, config: dict) -> None:
        cfg = my_cfg(config, self.name)
        input_key = cfg.get("input_key", "result.scores")
        output_key = cfg.get("output_key", f"group.{input_key}.mean")

        arrays: list[np.ndarray] = []
        contributing: list[str] = []
        for sr in group.subjects:
            value = resolve_subject_key(sr.context, input_key)
            if value is None:
                logger.warning(
                    "voxelwise_mean: subject %s missing key '%s' — skipping",
                    sr.subject, input_key)
                continue
            arr = np.asarray(value)
            arrays.append(arr)
            contributing.append(sr.subject)

        if not arrays:
            raise ValueError(
                f"voxelwise_mean: no subjects produced key '{input_key}'")

        shapes = {a.shape for a in arrays}
        if len(shapes) > 1:
            raise ValueError(
                f"voxelwise_mean: subject arrays have inconsistent shapes "
                f"under '{input_key}': {sorted(shapes)}"
            )

        stacked = np.stack(arrays, axis=0)
        mean = stacked.mean(axis=0)
        # Sample SEM; ddof=1 for the unbiased estimator. Falls back to 0
        # when only a single subject contributes.
        if stacked.shape[0] > 1:
            sem = stacked.std(axis=0, ddof=1) / np.sqrt(stacked.shape[0])
        else:
            sem = np.zeros_like(mean)

        group.put(output_key, mean)
        group.put(f"{output_key}.sem", sem)
        group.put(f"{output_key}.n_subjects", len(arrays))
        group.put(f"{output_key}.subjects", contributing)

    def validate_config(self, config: dict) -> list[str]:
        return []
