"""Response reader classes and registry."""
from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np

from denizenspipeline.plugins._decorators import (
    response_reader,
    _response_readers,
)


def get_reader(name: str):
    """Look up a reader by name, return an instance. Raises ValueError if not found."""
    if name not in _response_readers:
        available = ", ".join(sorted(_response_readers))
        raise ValueError(
            f"Unknown response reader '{name}'. Available: {available}")
    return _response_readers[name]()


def list_readers() -> list[str]:
    """Return sorted list of registered reader names."""
    return sorted(_response_readers)


# -- Built-in readers ---------------------------------------------------------


@response_reader("npz_per_run")
class NpzPerRunReader:
    """One .npz file per run. Key controlled by config['npz_key']."""

    name = "npz_per_run"

    def read(
        self, resp_dir: Path, run_names: list[str] | None, config: dict,
    ) -> dict[str, np.ndarray]:
        key = config.get("npz_key", "data")
        responses: dict[str, np.ndarray] = {}

        if run_names is not None:
            for name in run_names:
                f = resp_dir / f"{name}.npz"
                if f.exists():
                    responses[name] = np.load(f)[key]
        else:
            for f in sorted(resp_dir.glob("*.npz")):
                responses[f.stem] = np.load(f)[key]

        return responses

    def validate_config(self, config: dict) -> list[str]:
        return []


@response_reader("hdf5_per_run")
class Hdf5PerRunReader:
    """One .hdf5 file per run. Key controlled by config['hdf5_key']."""

    name = "hdf5_per_run"

    def read(
        self, resp_dir: Path, run_names: list[str] | None, config: dict,
    ) -> dict[str, np.ndarray]:
        import h5py

        key = config.get("hdf5_key", "data")
        responses: dict[str, np.ndarray] = {}

        if run_names is not None:
            for name in run_names:
                f = resp_dir / f"{name}.hdf5"
                if f.exists():
                    with h5py.File(f, "r") as h:
                        responses[name] = h[key][:]
        else:
            for f in sorted(resp_dir.glob("*.hdf5")):
                with h5py.File(f, "r") as h:
                    responses[f.stem] = h[key][:]

        return responses

    def validate_config(self, config: dict) -> list[str]:
        return []


@response_reader("single_pickle")
class SinglePickleReader:
    """All runs in a single pickle file (dict keyed by run name).

    If resp_dir is a file, load it directly. Otherwise look for a single
    .pkl file in the directory.  ``config['pickle_key']`` optionally
    indexes into a nested dict before accessing run keys.
    """

    name = "single_pickle"

    def read(
        self, resp_dir: Path, run_names: list[str] | None, config: dict,
    ) -> dict[str, np.ndarray]:
        if resp_dir.is_file():
            pkl_path = resp_dir
        else:
            pkl_files = sorted(resp_dir.glob("*.pkl"))
            if not pkl_files:
                return {}
            pkl_path = pkl_files[0]

        with open(pkl_path, "rb") as fh:
            all_data = pickle.load(fh)

        pickle_key = config.get("pickle_key")
        if pickle_key:
            all_data = all_data[pickle_key]

        responses: dict[str, np.ndarray] = {}
        if run_names is not None:
            for name in run_names:
                if name in all_data:
                    responses[name] = np.asarray(all_data[name])
        else:
            for name, arr in all_data.items():
                responses[name] = np.asarray(arr)

        return responses

    def validate_config(self, config: dict) -> list[str]:
        return []


@response_reader("single_hdf5")
class SingleHdf5Reader:
    """All runs in a single .hdf5 file (one dataset per run).

    If resp_dir is a file, load it directly. Otherwise look for a single
    .hdf5 file in the directory.  ``config['hdf5_key']`` is used as a
    group prefix (e.g. ``"data/"`` -> datasets ``"data/story1"``).
    """

    name = "single_hdf5"

    def read(
        self, resp_dir: Path, run_names: list[str] | None, config: dict,
    ) -> dict[str, np.ndarray]:
        import h5py

        if resp_dir.is_file():
            h5_path = resp_dir
        else:
            h5_files = sorted(resp_dir.glob("*.hdf5"))
            if not h5_files:
                return {}
            h5_path = h5_files[0]

        prefix = config.get("hdf5_key", "")
        if prefix and not prefix.endswith("/"):
            prefix += "/"

        responses: dict[str, np.ndarray] = {}
        with h5py.File(h5_path, "r") as h:
            if run_names is not None:
                for name in run_names:
                    ds_name = f"{prefix}{name}" if prefix else name
                    if ds_name in h:
                        responses[name] = h[ds_name][:]
            else:
                # Discover datasets (at prefix level or root)
                group = h[prefix.rstrip("/")] if prefix else h
                for ds_name in group:
                    if isinstance(group[ds_name], h5py.Dataset):
                        responses[ds_name] = group[ds_name][:]

        return responses

    def validate_config(self, config: dict) -> list[str]:
        return []


@response_reader("auto")
class AutoReader:
    """Auto-detect format: try hdf5_per_run first, then npz_per_run."""

    name = "auto"

    def read(
        self, resp_dir: Path, run_names: list[str] | None, config: dict,
    ) -> dict[str, np.ndarray]:
        # Try HDF5 files first
        hdf5_reader = Hdf5PerRunReader()
        responses = hdf5_reader.read(resp_dir, run_names, config)
        if responses:
            return responses

        # Fall back to NPZ
        npz_reader = NpzPerRunReader()
        return npz_reader.read(resp_dir, run_names, config)

    def validate_config(self, config: dict) -> list[str]:
        return []
