"""Voxelwise count of subjects passing a significance threshold.

Replicates the consistency map from Deniz 2019 Fig 3c/d: per voxel, how
many subjects show a significant effect. Reads per-subject p-value (or
score-vs-null) arrays in a common space.
"""

from __future__ import annotations

import logging

import numpy as np

from fmriflow.core.group_types import GroupResult
from fmriflow.modules._decorators import group_analyzer
from fmriflow.modules.group_analyzers._helpers import my_cfg, resolve_subject_key

logger = logging.getLogger(__name__)


@group_analyzer("significance_count")
class SignificanceCountAnalyzer:
    """Count subjects with a per-voxel value passing a threshold.

    Two thresholding modes:

    - ``below`` (default) — count voxels where ``input_key <= threshold``.
      Suitable for p-value maps.
    - ``above`` — count voxels where ``input_key >= threshold``. Suitable
      for prediction accuracy maps with a fixed cutoff.

    Writes ``group.<output_key>`` (integer count per voxel) and
    ``group.<output_key>.n_subjects`` (number of contributing subjects).
    """

    name = "significance_count"
    produces_subject_artifact = False
    PARAM_SCHEMA = {
        "input_key": {
            "type": "str",
            "default": "result.scores",
            "description": "Dotted path into each subject's context.",
        },
        "threshold": {
            "type": "float",
            "default": 0.05,
            "description": "Threshold for passing — interpreted by 'mode'.",
        },
        "mode": {
            "type": "str",
            "default": "below",
            "description": "'below' (p-values) or 'above' (accuracy maps).",
        },
        "output_key": {
            "type": "str",
            "description": "Group-artifact key for the count map.",
        },
    }

    def analyze(self, group: GroupResult, config: dict) -> None:
        cfg = my_cfg(config, self.name)
        input_key = cfg.get("input_key", "result.scores")
        threshold = float(cfg.get("threshold", 0.05))
        mode = cfg.get("mode", "below")
        output_key = cfg.get(
            "output_key", f"group.{input_key}.n_significant")

        if mode not in ("below", "above"):
            raise ValueError(
                f"significance_count: invalid mode '{mode}', "
                f"must be 'below' or 'above'")

        count: np.ndarray | None = None
        contributing: list[str] = []
        shape: tuple[int, ...] | None = None

        for sr in group.subjects:
            value = resolve_subject_key(sr.context, input_key)
            if value is None:
                logger.warning(
                    "significance_count: subject %s missing key '%s'",
                    sr.subject, input_key)
                continue
            arr = np.asarray(value)
            if shape is None:
                shape = arr.shape
                count = np.zeros(shape, dtype=np.int32)
            elif arr.shape != shape:
                raise ValueError(
                    f"significance_count: subject {sr.subject} shape "
                    f"{arr.shape} differs from {shape} under '{input_key}'"
                )
            passes = arr <= threshold if mode == "below" else arr >= threshold
            count += passes.astype(np.int32)
            contributing.append(sr.subject)

        if count is None:
            raise ValueError(
                f"significance_count: no subjects produced key '{input_key}'")

        group.put(output_key, count)
        group.put(f"{output_key}.n_subjects", len(contributing))
        group.put(f"{output_key}.subjects", contributing)
        group.put(f"{output_key}.threshold", threshold)
        group.put(f"{output_key}.mode", mode)

    def validate_config(self, config: dict) -> list[str]:
        cfg = my_cfg(config, self.name)
        mode = cfg.get("mode", "below")
        if mode not in ("below", "above"):
            return [f"significance_count.mode must be 'below' or 'above', got '{mode}'"]
        return []
