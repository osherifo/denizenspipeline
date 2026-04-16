"""Tests for response readers and LocalResponseLoader integration."""

import pickle

import numpy as np
import pytest

from fmriflow.modules.response_loaders.readers import (
    _response_readers,
    get_reader,
    list_readers,
    response_reader,
)
from fmriflow.modules.response_loaders.local import LocalResponseLoader

N_TRS = 50
N_VOXELS = 20
RUN_NAMES = ["story1", "story2", "story3"]


@pytest.fixture
def rng():
    return np.random.RandomState(42)


@pytest.fixture
def arrays(rng):
    """Dict of run_name -> (n_trs, n_voxels) arrays."""
    return {name: rng.randn(N_TRS, N_VOXELS).astype(np.float32)
            for name in RUN_NAMES}


# ── npz_per_run ──────────────────────────────────────────────────


class TestNpzPerRunReader:
    def test_loads_all_runs(self, tmp_path, arrays):
        for name, arr in arrays.items():
            np.savez_compressed(tmp_path / f"{name}.npz", data=arr)

        reader = get_reader("npz_per_run")
        result = reader.read(tmp_path, None, {})

        assert set(result.keys()) == set(RUN_NAMES)
        for name in RUN_NAMES:
            np.testing.assert_array_equal(result[name], arrays[name])

    def test_custom_npz_key(self, tmp_path, arrays):
        for name, arr in arrays.items():
            np.savez_compressed(tmp_path / f"{name}.npz", responses=arr)

        reader = get_reader("npz_per_run")
        result = reader.read(tmp_path, None, {"npz_key": "responses"})

        assert set(result.keys()) == set(RUN_NAMES)
        for name in RUN_NAMES:
            np.testing.assert_array_equal(result[name], arrays[name])


# ── hdf5_per_run ─────────────────────────────────────────────────


class TestHdf5PerRunReader:
    def test_loads_all_runs(self, tmp_path, arrays):
        h5py = pytest.importorskip("h5py")
        for name, arr in arrays.items():
            with h5py.File(tmp_path / f"{name}.hdf5", "w") as h:
                h.create_dataset("data", data=arr)

        reader = get_reader("hdf5_per_run")
        result = reader.read(tmp_path, None, {})

        assert set(result.keys()) == set(RUN_NAMES)
        for name in RUN_NAMES:
            np.testing.assert_array_equal(result[name], arrays[name])


# ── single_pickle ────────────────────────────────────────────────


class TestSinglePickleReader:
    def test_loads_all_runs(self, tmp_path, arrays):
        pkl_path = tmp_path / "responses.pkl"
        with open(pkl_path, "wb") as f:
            pickle.dump(arrays, f)

        reader = get_reader("single_pickle")
        result = reader.read(tmp_path, None, {})

        assert set(result.keys()) == set(RUN_NAMES)
        for name in RUN_NAMES:
            np.testing.assert_array_equal(result[name], arrays[name])

    def test_with_pickle_key(self, tmp_path, arrays):
        nested = {"brain_data": arrays}
        pkl_path = tmp_path / "responses.pkl"
        with open(pkl_path, "wb") as f:
            pickle.dump(nested, f)

        reader = get_reader("single_pickle")
        result = reader.read(tmp_path, None, {"pickle_key": "brain_data"})

        assert set(result.keys()) == set(RUN_NAMES)
        for name in RUN_NAMES:
            np.testing.assert_array_equal(result[name], arrays[name])

    def test_direct_file_path(self, tmp_path, arrays):
        pkl_path = tmp_path / "my_responses.pkl"
        with open(pkl_path, "wb") as f:
            pickle.dump(arrays, f)

        reader = get_reader("single_pickle")
        result = reader.read(pkl_path, None, {})

        assert set(result.keys()) == set(RUN_NAMES)


# ── single_hdf5 ─────────────────────────────────────────────────


class TestSingleHdf5Reader:
    def test_loads_all_runs(self, tmp_path, arrays):
        h5py = pytest.importorskip("h5py")
        h5_path = tmp_path / "all_responses.hdf5"
        with h5py.File(h5_path, "w") as h:
            for name, arr in arrays.items():
                h.create_dataset(name, data=arr)

        reader = get_reader("single_hdf5")
        result = reader.read(tmp_path, None, {})

        assert set(result.keys()) == set(RUN_NAMES)
        for name in RUN_NAMES:
            np.testing.assert_array_equal(result[name], arrays[name])


# ── auto reader ──────────────────────────────────────────────────


class TestAutoReader:
    def test_detects_npz(self, tmp_path, arrays):
        for name, arr in arrays.items():
            np.savez_compressed(tmp_path / f"{name}.npz", data=arr)

        reader = get_reader("auto")
        result = reader.read(tmp_path, None, {})

        assert set(result.keys()) == set(RUN_NAMES)

    def test_detects_hdf5(self, tmp_path, arrays):
        h5py = pytest.importorskip("h5py")
        for name, arr in arrays.items():
            with h5py.File(tmp_path / f"{name}.hdf5", "w") as h:
                h.create_dataset("data", data=arr)

        reader = get_reader("auto")
        result = reader.read(tmp_path, None, {})

        assert set(result.keys()) == set(RUN_NAMES)


# ── Registry ─────────────────────────────────────────────────────


class TestRegistry:
    def test_list_readers(self):
        names = list_readers()
        assert "auto" in names
        assert "npz_per_run" in names
        assert "hdf5_per_run" in names
        assert "single_pickle" in names
        assert "single_hdf5" in names
        assert len(names) >= 5

    def test_unknown_reader_raises(self):
        with pytest.raises(ValueError, match="Unknown response reader"):
            get_reader("nonexistent_format")

    def test_custom_reader_registration(self, tmp_path):
        @response_reader("test_custom")
        class CustomReader:
            def read(self, resp_dir, run_names, config):
                return {"custom_run": np.zeros((10, 5))}

        try:
            reader = get_reader("test_custom")
            result = reader.read(tmp_path, None, {})
            assert "custom_run" in result
            assert result["custom_run"].shape == (10, 5)
        finally:
            # Clean up to avoid polluting other tests
            _response_readers.pop("test_custom", None)


# ── LocalResponseLoader integration ─────────────────────────────


class TestLocalLoaderWithReader:
    def test_end_to_end_npz(self, tmp_path, arrays):
        for name, arr in arrays.items():
            np.savez_compressed(tmp_path / f"{name}.npz", data=arr)

        config = {
            "response": {
                "path": str(tmp_path),
                "reader": "npz_per_run",
            },
            "subject_config": {},
        }
        loader = LocalResponseLoader()
        result = loader.load(config)

        assert set(result.responses.keys()) == set(RUN_NAMES)
        for name in RUN_NAMES:
            assert result.responses[name].shape[0] == N_TRS
