"""Tests for BootstrapRidgeModel."""

import numpy as np
import pytest

from fmriflow.core.types import ModelResult, PreparedData
from fmriflow.modules.models.ridge import BootstrapRidgeModel


@pytest.fixture
def small_prepared_data():
    rng = np.random.RandomState(42)
    n_features = 3
    n_voxels = 5
    delays = [1, 2]
    n_delayed = n_features * len(delays)
    n_train, n_test = 100, 30

    true_weights = rng.randn(n_delayed, n_voxels).astype(np.float32)
    X_train = rng.randn(n_train, n_delayed).astype(np.float32)
    Y_train = X_train @ true_weights + rng.randn(n_train, n_voxels).astype(np.float32) * 0.2
    X_test = rng.randn(n_test, n_delayed).astype(np.float32)
    Y_test = X_test @ true_weights + rng.randn(n_test, n_voxels).astype(np.float32) * 0.2

    return PreparedData(
        X_train=X_train, Y_train=Y_train,
        X_test=X_test, Y_test=Y_test,
        feature_names=["f1"],
        feature_dims=[n_features],
        delays=delays,
        train_runs=["s1", "s2"],
        test_runs=["s3"],
    )


class TestBootstrapRidgeModel:
    def test_fit_returns_model_result(self, small_prepared_data):
        model = BootstrapRidgeModel()
        config = {
            "model": {
                "params": {
                    "alphas": "logspace(0,2,5)",
                    "n_boots": 2,
                    "chunk_len": 10,
                    "n_chunks": 2,
                },
            },
        }
        result = model.fit(small_prepared_data, config)
        assert isinstance(result, ModelResult)

    def test_output_shapes(self, small_prepared_data):
        model = BootstrapRidgeModel()
        config = {
            "model": {
                "params": {
                    "alphas": "logspace(0,2,3)",
                    "n_boots": 2,
                    "chunk_len": 10,
                    "n_chunks": 2,
                },
            },
        }
        result = model.fit(small_prepared_data, config)
        n_delayed = small_prepared_data.X_train.shape[1]
        n_voxels = small_prepared_data.Y_train.shape[1]
        assert result.weights.shape == (n_delayed, n_voxels)
        assert result.scores.shape == (n_voxels,)
        assert result.alphas.shape == (n_voxels,)

    def test_metadata_propagated(self, small_prepared_data):
        model = BootstrapRidgeModel()
        config = {"model": {"params": {"n_boots": 2, "chunk_len": 10, "n_chunks": 2}}}
        result = model.fit(small_prepared_data, config)
        assert result.feature_names == small_prepared_data.feature_names
        assert result.delays == small_prepared_data.delays


class TestResolveAlphas:
    def test_logspace_string(self):
        model = BootstrapRidgeModel()
        alphas = model._resolve_alphas("logspace(1,3,10)")
        assert len(alphas) == 10
        np.testing.assert_allclose(alphas[0], 10.0)
        np.testing.assert_allclose(alphas[-1], 1000.0)

    def test_list_input(self):
        model = BootstrapRidgeModel()
        alphas = model._resolve_alphas([1, 10, 100])
        assert len(alphas) == 3
        np.testing.assert_array_equal(alphas, [1, 10, 100])


class TestValidateConfig:
    def test_bad_n_boots(self):
        model = BootstrapRidgeModel()
        errors = model.validate_config({"model": {"params": {"n_boots": -1}}})
        assert any("n_boots" in e for e in errors)

    def test_string_n_boots(self):
        model = BootstrapRidgeModel()
        errors = model.validate_config({"model": {"params": {"n_boots": "bad"}}})
        assert any("n_boots" in e for e in errors)

    def test_valid_config(self):
        model = BootstrapRidgeModel()
        errors = model.validate_config({"model": {"params": {"n_boots": 10}}})
        assert errors == []

    def test_default_config(self):
        model = BootstrapRidgeModel()
        errors = model.validate_config({})
        assert errors == []
