"""WeightsReporter — saves model weights to HDF5."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from fmriflow.core.types import ModelResult
from fmriflow.modules._decorators import reporter


def _to_numpy(arr) -> np.ndarray:
    """Coerce cupy / torch / numpy → numpy on CPU.

    Multiple-kernel-ridge fits on GPU produce cupy arrays; h5py refuses
    implicit conversion. Call this on every array the reporter writes.
    """
    if hasattr(arr, "get") and callable(arr.get):
        # cupy.ndarray.get() copies to host. Plain np arrays don't have .get;
        # h5py datasets do — guard against that.
        try:
            return np.asarray(arr.get())
        except TypeError:
            pass
    if hasattr(arr, "detach") and hasattr(arr, "cpu"):
        return arr.detach().cpu().numpy()         # torch tensor
    return np.asarray(arr)


@reporter("weights")
class WeightsReporter:
    """Saves model weights to HDF5."""

    name = "weights"
    PARAM_SCHEMA = {}

    def report(self, result: ModelResult, context, config: dict) -> dict[str, str]:
        import h5py

        output_dir = Path(config.get('reporting', {}).get('output_dir', './results'))
        output_dir.mkdir(parents=True, exist_ok=True)

        path = output_dir / 'weights.hdf5'
        with h5py.File(path, 'w') as f:
            f.create_dataset('weights', data=_to_numpy(result.weights))
            f.create_dataset('scores', data=_to_numpy(result.scores))
            f.create_dataset('alphas', data=_to_numpy(result.alphas))
            f.attrs['feature_names'] = list(result.feature_names)
            f.attrs['feature_dims'] = list(result.feature_dims)
            f.attrs['delays'] = list(result.delays)

        return {'weights': str(path)}

    def validate_config(self, config: dict) -> list[str]:
        return []
