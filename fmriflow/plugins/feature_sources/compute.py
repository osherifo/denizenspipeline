"""ComputeSource — runs a FeatureExtractor to compute features fresh."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from fmriflow.core.types import FeatureSet, StimulusData
from fmriflow.plugins._decorators import feature_source

logger = logging.getLogger(__name__)


@feature_source("compute")
class ComputeSource:
    """Compute features using a FeatureExtractor.

    The default source. Looks up the extractor from the registry,
    runs it against stimuli, and optionally saves the result via save_to.
    """

    name = "compute"
    PARAM_SCHEMA = {
        "extractor": {"type": "string", "description": "Feature extractor to use"},
        "params": {"type": "dict", "default": {}, "description": "Parameters passed to the extractor"},
        "name": {"type": "string", "description": "Override feature name"},
        "save_to": {"type": "dict", "description": "Save extracted features: {backend, path/bucket, prefix}"},
    }

    def __init__(self):
        self.extractor = None
        self.stimuli = None

    def set_extractor(self, extractor):
        """Set the feature extractor to use."""
        self.extractor = extractor

    def set_stimuli(self, stimuli: StimulusData):
        """Set the stimulus data for extraction."""
        self.stimuli = stimuli

    def load(self, run_names: list[str], config: dict) -> FeatureSet:
        """Extract features from stimuli using the configured extractor."""
        params = config.get('params', {})
        feature_set = self.extractor.extract(self.stimuli, run_names, params)

        for run_name in sorted(feature_set.data):
            shape = feature_set.data[run_name].shape
            logger.info("  %-30s  %s  shape=%s", feature_set.name, run_name, shape)

        # Override the name if the config specifies a different one
        if config.get('name') and config['name'] != self.extractor.name:
            feature_set = FeatureSet(
                name=config['name'],
                data=feature_set.data,
                n_dims=feature_set.n_dims,
                metadata=feature_set.metadata,
            )

        # Optionally save to a backend for future reuse
        save_to = config.get('save_to')
        if save_to:
            self._save(feature_set, save_to)

        return feature_set

    def validate_config(self, config: dict) -> list[str]:
        if self.extractor:
            return self.extractor.validate_config(config.get('params', {}))
        return []

    def _save(self, feature_set: FeatureSet, save_config: dict) -> None:
        """Save extracted features to a backend."""
        backend = save_config['backend']
        if backend == 'filesystem':
            path = Path(save_config['path'])
            path.mkdir(parents=True, exist_ok=True)
            for run_name, arr in feature_set.data.items():
                np.savez_compressed(path / f"{run_name}.npz", data=arr)
        elif backend == 'cloud':
            import cottoncandy as cc
            cci = cc.get_interface(save_config['bucket'])
            prefix = save_config.get('prefix', '')
            for run_name, arr in feature_set.data.items():
                cci.upload_raw_array(f"{prefix}{run_name}", arr)
