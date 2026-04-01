"""Weight analysis — decomposes and summarizes model weights."""

from __future__ import annotations

import logging

import numpy as np

from denizenspipeline.core.array_utils import undelay_weights
from denizenspipeline.core.types import ModelResult, WeightAnalysis
from denizenspipeline.plugins._decorators import analyzer

logger = logging.getLogger(__name__)


@analyzer("weight_analysis")
class WeightAnalysisAnalyzer:
    """Decomposes the delayed weight matrix into per-feature importance
    and temporal profiles.

    Stores result in context as ``analysis.weight_analysis``.
    """

    name = "weight_analysis"
    PARAM_SCHEMA = {
        "normalize": {"type": "bool", "default": False, "description": "Normalize per-feature importance"},
    }

    def analyze(self, context, config: dict) -> None:
        result = context.get('result', ModelResult)
        acfg = self._get_config(config)
        normalize = acfg.get('normalize', False)

        # (n_delays, n_features, n_voxels)
        undelayed = undelay_weights(result.weights, result.delays)

        # Per-feature importance: L2 norm across delays
        # undelayed shape: (n_delays, n_features, n_voxels)
        per_feature = np.sqrt((undelayed ** 2).sum(axis=0))

        if normalize:
            total = per_feature.sum(axis=0, keepdims=True)
            total = np.where(total == 0, 1, total)
            per_feature = per_feature / total

        context.put('analysis.weight_analysis', WeightAnalysis(
            per_feature_importance=per_feature,
            temporal_profiles=undelayed,
            feature_names=result.feature_names,
            delays=result.delays,
        ))
        logger.info("Weight analysis: %d features, %d delays",
                     len(result.feature_names), len(result.delays))

    def validate_config(self, config: dict) -> list[str]:
        return []

    @staticmethod
    def _get_config(config: dict) -> dict:
        for acfg in config.get('analysis', []):
            if acfg.get('name') == 'weight_analysis':
                return acfg.get('params', {})
        return {}
