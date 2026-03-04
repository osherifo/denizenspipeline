"""FilesystemSource — loads pre-extracted features from local files."""

from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np

from denizenspipeline.core.types import FeatureSet
from denizenspipeline.plugins._decorators import feature_source


@feature_source("filesystem")
class FilesystemSource:
    """Load pre-extracted features from local filesystem.

    Covers v1 patterns:
    - reload_stimulus_features() loading .npz per run
    - phrasal_contextual() loading giant pickle of hidden states
    - use_presaved_moten=True

    Config keys:
        path: base directory or file path
        format: 'npz' | 'hdf5' | 'pickle' (default: 'npz')
        name: feature name
        file_pattern: pattern for filenames (default: '{run}')
        npz_key: key within .npz file (default: 'data')
        pickle_key: key within pickle dict (optional)
        layer: sub-select a layer from nested data (optional)
    """

    name = "filesystem"

    def load(self, run_names: list[str], config: dict) -> FeatureSet:
        path = Path(config['path'])
        fmt = config.get('format', 'npz')
        feature_name = config['name']
        file_pattern = config.get('file_pattern', '{run}')

        data = {}
        if fmt == 'pickle' and path.is_file():
            data = self._load_from_pickle(path, run_names, config)
        else:
            for run_name in run_names:
                filename = file_pattern.format(run=run_name)
                data[run_name] = self._load_single(path, filename, fmt, config)

        n_dims = next(iter(data.values())).shape[1]
        return FeatureSet(name=feature_name, data=data, n_dims=n_dims)

    def validate_config(self, config: dict) -> list[str]:
        errors = []
        if 'path' not in config:
            errors.append("filesystem source requires 'path'")
        elif not Path(config['path']).exists():
            errors.append(f"Path not found: {config['path']}")
        return errors

    def _load_single(self, base_path, filename, fmt, config):
        if fmt == 'npz':
            f = base_path / f"{filename}.npz"
            key = config.get('npz_key', 'data')
            return np.load(f)[key]
        elif fmt == 'hdf5':
            import h5py
            f = base_path / f"{filename}.hdf5"
            key = config.get('dataset_key', 'data')
            with h5py.File(f, 'r') as h:
                return h[key][:]
        elif fmt == 'pickle':
            f = base_path / f"{filename}.pkl"
            with open(f, 'rb') as h:
                return pickle.load(h)
        else:
            raise ValueError(f"Unknown format: {fmt}")

    def _load_from_pickle(self, path, run_names, config):
        """Handle the v1 pattern: single pickle with all runs."""
        with open(path, 'rb') as f:
            all_data = pickle.load(f)

        pickle_key = config.get('pickle_key')
        if pickle_key:
            all_data = all_data[pickle_key]

        layer = config.get('layer')
        data = {}
        for run_name in run_names:
            for key_variant in [run_name, f"{run_name}.txt", run_name.lower()]:
                if key_variant in all_data:
                    run_data = all_data[key_variant]
                    if layer is not None and isinstance(run_data, dict):
                        run_data = run_data[layer]
                    if isinstance(run_data, list):
                        run_data = np.array(run_data)
                    if run_data.ndim == 1:
                        run_data = run_data.reshape(-1, 1)
                    data[run_name] = run_data
                    break
        return data
