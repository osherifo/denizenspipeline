"""WeightsReporter — saves model weights to HDF5."""

from __future__ import annotations

from pathlib import Path

from denizenspipeline.core.types import ModelResult


class WeightsReporter:
    """Saves model weights to HDF5."""

    name = "weights"

    def report(self, result: ModelResult, context, config: dict) -> dict[str, str]:
        import h5py

        output_dir = Path(config.get('reporting', {}).get('output_dir', './results'))
        output_dir.mkdir(parents=True, exist_ok=True)

        path = output_dir / 'weights.hdf5'
        with h5py.File(path, 'w') as f:
            f.create_dataset('weights', data=result.weights)
            f.create_dataset('scores', data=result.scores)
            f.create_dataset('alphas', data=result.alphas)
            f.attrs['feature_names'] = result.feature_names
            f.attrs['feature_dims'] = result.feature_dims
            f.attrs['delays'] = result.delays

        return {'weights': str(path)}

    def validate_config(self, config: dict) -> list[str]:
        return []
