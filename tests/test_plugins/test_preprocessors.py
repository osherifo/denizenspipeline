"""Tests for DefaultPreprocessor."""

import numpy as np
import pytest

from fmriflow.core.types import (
    FeatureData,
    FeatureSet,
    PreparedData,
    ResponseData,
)
from fmriflow.plugins.preprocessors.default import DefaultPreprocessor
from tests.conftest import N_FEATURES, N_TRS, N_VOXELS, RUN_NAMES


@pytest.fixture
def prep_config():
    return {
        "split": {"test_runs": ["story3"]},
        "preprocessing": {
            "trim_start": 5,
            "trim_end": 5,
            "delays": [1, 2, 3, 4],
            "zscore": True,
        },
    }


@pytest.fixture
def prep_responses():
    rng = np.random.RandomState(0)
    return ResponseData(
        responses={
            name: rng.randn(N_TRS, N_VOXELS).astype(np.float32)
            for name in RUN_NAMES
        },
        mask=np.ones(N_VOXELS, dtype=bool),
        surface="s",
        transform="t",
    )


@pytest.fixture
def prep_features():
    rng = np.random.RandomState(1)
    fs = FeatureSet(
        name="feat",
        data={name: rng.randn(N_TRS, N_FEATURES).astype(np.float32) for name in RUN_NAMES},
        n_dims=N_FEATURES,
    )
    return FeatureData(features={"feat": fs})


class TestDefaultPreprocessor:
    def test_output_type(self, prep_responses, prep_features, prep_config):
        prep = DefaultPreprocessor()
        result = prep.prepare(prep_responses, prep_features, prep_config)
        assert isinstance(result, PreparedData)

    def test_output_shapes(self, prep_responses, prep_features, prep_config):
        prep = DefaultPreprocessor()
        result = prep.prepare(prep_responses, prep_features, prep_config)

        trim_start = 5
        trim_end = 5
        trs_per_run = N_TRS - trim_start - trim_end
        n_train_runs = 2  # story1, story2
        n_test_runs = 1   # story3
        delays = [1, 2, 3, 4]
        n_delayed = N_FEATURES * len(delays)

        assert result.X_train.shape == (n_train_runs * trs_per_run, n_delayed)
        assert result.Y_train.shape == (n_train_runs * trs_per_run, N_VOXELS)
        assert result.X_test.shape == (n_test_runs * trs_per_run, n_delayed)
        assert result.Y_test.shape == (n_test_runs * trs_per_run, N_VOXELS)

    def test_train_test_split(self, prep_responses, prep_features, prep_config):
        prep = DefaultPreprocessor()
        result = prep.prepare(prep_responses, prep_features, prep_config)
        assert "story3" in result.test_runs
        assert "story3" not in result.train_runs
        assert "story1" in result.train_runs
        assert "story2" in result.train_runs

    def test_no_trimming(self, prep_responses, prep_features, prep_config):
        prep_config["preprocessing"]["trim_start"] = 0
        prep_config["preprocessing"]["trim_end"] = 0
        prep = DefaultPreprocessor()
        result = prep.prepare(prep_responses, prep_features, prep_config)
        n_train_runs = 2
        assert result.Y_train.shape[0] == n_train_runs * N_TRS

    def test_validate_config_missing_test_runs(self):
        prep = DefaultPreprocessor()
        errors = prep.validate_config({})
        assert any("test_runs" in e for e in errors)

    def test_validate_config_valid(self, prep_config):
        prep = DefaultPreprocessor()
        errors = prep.validate_config(prep_config)
        assert errors == []

    def test_feature_metadata_preserved(self, prep_responses, prep_features, prep_config):
        prep = DefaultPreprocessor()
        result = prep.prepare(prep_responses, prep_features, prep_config)
        assert result.feature_names == ["feat"]
        assert result.feature_dims == [N_FEATURES]
        assert result.delays == [1, 2, 3, 4]

    def test_tr_mismatch_raises_value_error(self, prep_config):
        """A per-run TR mismatch between responses and features raises ValueError."""
        rng = np.random.RandomState(0)
        responses = ResponseData(
            responses={
                name: rng.randn(N_TRS, N_VOXELS).astype(np.float32)
                for name in RUN_NAMES
            },
            mask=np.ones(N_VOXELS, dtype=bool),
            surface="s",
            transform="t",
        )
        # Features for "story1" have one extra TR to trigger a mismatch
        fs = FeatureSet(
            name="feat",
            data={
                name: rng.randn(
                    N_TRS + (1 if name == "story1" else 0), N_FEATURES
                ).astype(np.float32)
                for name in RUN_NAMES
            },
            n_dims=N_FEATURES,
        )
        features = FeatureData(features={"feat": fs})

        prep = DefaultPreprocessor()
        with pytest.raises(ValueError, match="Row mismatch in run 'story1'"):
            prep.prepare(responses, features, prep_config)
