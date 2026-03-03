"""Response reader registry and built-in readers."""
from __future__ import annotations

import pickle
from pathlib import Path
from typing import Callable

import numpy as np

ReaderFn = Callable[[Path, "list[str] | None", dict], "dict[str, np.ndarray]"]

_READERS: dict[str, ReaderFn] = {}


def response_reader(name: str):
    """Decorator to register a response reader function."""
    def decorator(fn: ReaderFn) -> ReaderFn:
        _READERS[name] = fn
        return fn
    return decorator


def get_reader(name: str) -> ReaderFn:
    """Look up a reader by name. Raises ValueError if not found."""
    if name not in _READERS:
        available = ", ".join(sorted(_READERS))
        raise ValueError(
            f"Unknown response reader '{name}'. Available: {available}")
    return _READERS[name]


def list_readers() -> list[str]:
    """Return sorted list of registered reader names."""
    return sorted(_READERS)


# ── Built-in readers ─────────────────────────────────────────────


@response_reader("npz_per_run")
def _read_npz_per_run(
    resp_dir: Path, run_names: list[str] | None, config: dict,
) -> dict[str, np.ndarray]:
    """One .npz file per run. Key controlled by config['npz_key']."""
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


@response_reader("hdf5_per_run")
def _read_hdf5_per_run(
    resp_dir: Path, run_names: list[str] | None, config: dict,
) -> dict[str, np.ndarray]:
    """One .hdf5 file per run. Key controlled by config['hdf5_key']."""
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


@response_reader("single_pickle")
def _read_single_pickle(
    resp_dir: Path, run_names: list[str] | None, config: dict,
) -> dict[str, np.ndarray]:
    """All runs in a single pickle file (dict keyed by run name).

    If resp_dir is a file, load it directly. Otherwise look for a single
    .pkl file in the directory.  ``config['pickle_key']`` optionally
    indexes into a nested dict before accessing run keys.
    """
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


@response_reader("single_hdf5")
def _read_single_hdf5(
    resp_dir: Path, run_names: list[str] | None, config: dict,
) -> dict[str, np.ndarray]:
    """All runs in a single .hdf5 file (one dataset per run).

    If resp_dir is a file, load it directly. Otherwise look for a single
    .hdf5 file in the directory.  ``config['hdf5_key']`` is used as a
    group prefix (e.g. ``"data/"`` -> datasets ``"data/story1"``).
    """
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


@response_reader("auto")
def _read_auto(
    resp_dir: Path, run_names: list[str] | None, config: dict,
) -> dict[str, np.ndarray]:
    """Auto-detect format: try hdf5_per_run first, then npz_per_run."""
    # Try HDF5 files first
    responses = _read_hdf5_per_run(resp_dir, run_names, config)
    if responses:
        return responses

    # Fall back to NPZ
    return _read_npz_per_run(resp_dir, run_names, config)
