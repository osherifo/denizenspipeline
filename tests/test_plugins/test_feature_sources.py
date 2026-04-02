"""Tests for feature sources."""

import numpy as np
import pytest

from fmriflow.core.types import FeatureSet, StimulusData
from fmriflow.plugins.feature_sources.compute import ComputeSource
from fmriflow.plugins.feature_sources.filesystem import FilesystemSource
from tests.conftest import N_FEATURES, N_TRS, RUN_NAMES


class TestFilesystemSource:
    def test_load_npz(self, npz_feature_dir):
        source = FilesystemSource()
        config = {
            "path": str(npz_feature_dir),
            "name": "test_feat",
            "format": "npz",
        }
        result = source.load(RUN_NAMES, config)
        assert isinstance(result, FeatureSet)
        assert result.name == "test_feat"
        assert result.n_dims == N_FEATURES
        for name in RUN_NAMES:
            assert name in result.data
            assert result.data[name].shape == (N_TRS, N_FEATURES)

    def test_validate_config_missing_path(self):
        source = FilesystemSource()
        errors = source.validate_config({})
        assert any("path" in e for e in errors)

    def test_validate_config_nonexistent_path(self, tmp_path):
        source = FilesystemSource()
        errors = source.validate_config({"path": str(tmp_path / "nope")})
        assert any("not found" in e.lower() or "Path" in e for e in errors)

    def test_validate_config_valid_path(self, npz_feature_dir):
        source = FilesystemSource()
        errors = source.validate_config({"path": str(npz_feature_dir)})
        assert errors == []


class TestComputeSource:
    def test_extract_and_return(self, mock_stimuli):
        class FakeExtractor:
            name = "fake"
            n_dims = 2
            def extract(self, stimuli, run_names, config):
                data = {rn: np.ones((N_TRS, 2)) for rn in run_names}
                return FeatureSet(name="fake", data=data, n_dims=2)
            def validate_config(self, config):
                return []

        source = ComputeSource()
        source.set_extractor(FakeExtractor())
        source.set_stimuli(mock_stimuli)

        config = {"name": "fake", "params": {}}
        result = source.load(RUN_NAMES, config)
        assert isinstance(result, FeatureSet)
        assert result.name == "fake"
        assert result.n_dims == 2

    def test_name_override(self, mock_stimuli):
        class FakeExtractor:
            name = "original"
            n_dims = 1
            def extract(self, stimuli, run_names, config):
                data = {rn: np.ones((N_TRS, 1)) for rn in run_names}
                return FeatureSet(name="original", data=data, n_dims=1)
            def validate_config(self, config):
                return []

        source = ComputeSource()
        source.set_extractor(FakeExtractor())
        source.set_stimuli(mock_stimuli)

        config = {"name": "custom_name", "params": {}}
        result = source.load(RUN_NAMES, config)
        assert result.name == "custom_name"

    def test_save_to_filesystem(self, tmp_path, mock_stimuli):
        class FakeExtractor:
            name = "saveable"
            n_dims = 3
            def extract(self, stimuli, run_names, config):
                data = {rn: np.ones((N_TRS, 3)) for rn in run_names}
                return FeatureSet(name="saveable", data=data, n_dims=3)
            def validate_config(self, config):
                return []

        source = ComputeSource()
        source.set_extractor(FakeExtractor())
        source.set_stimuli(mock_stimuli)

        save_dir = tmp_path / "saved_features"
        config = {
            "name": "saveable",
            "params": {},
            "save_to": {"backend": "filesystem", "path": str(save_dir)},
        }
        source.load(RUN_NAMES, config)

        # Verify saved files
        for name in RUN_NAMES:
            assert (save_dir / f"{name}.npz").exists()

    def test_validate_config_delegates(self):
        class StrictExtractor:
            name = "strict"
            n_dims = 1
            def extract(self, stimuli, run_names, config): ...
            def validate_config(self, config):
                return ["missing required param"]

        source = ComputeSource()
        source.set_extractor(StrictExtractor())
        errors = source.validate_config({"params": {}})
        assert len(errors) == 1
