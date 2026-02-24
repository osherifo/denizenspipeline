"""MetricsReporter — saves prediction accuracy metrics as JSON."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from denizenspipeline.core.types import ModelResult


class MetricsReporter:
    """Saves prediction accuracy metrics as JSON."""

    name = "metrics"

    def report(self, result: ModelResult, context, config: dict) -> dict[str, str]:
        output_dir = Path(config.get('reporting', {}).get('output_dir', './results'))
        output_dir.mkdir(parents=True, exist_ok=True)

        metrics = {
            'mean_score': float(result.scores.mean()),
            'median_score': float(np.median(result.scores)),
            'max_score': float(result.scores.max()),
            'n_voxels': result.n_voxels,
            'n_significant': int((result.scores > 0.1).sum()),
            'feature_names': result.feature_names,
            'feature_dims': result.feature_dims,
            'delays': result.delays,
        }

        path = output_dir / 'metrics.json'
        with open(path, 'w') as f:
            json.dump(metrics, f, indent=2)

        return {'metrics': str(path)}

    def validate_config(self, config: dict) -> list[str]:
        return []
