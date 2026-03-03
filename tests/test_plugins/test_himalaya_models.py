"""Tests for himalaya-based model plugins."""

import numpy as np
import pytest

from denizenspipeline.core.types import ModelResult, PreparedData
from denizenspipeline.plugins.models.himalaya import (
    BandedRidgeModel,
    HimalayaRidgeModel,
    MultipleKernelRidgeModel,
    _Delayer,
    _compute_group_labels,
    _compute_group_slices,
    _resolve_alphas,
    _score_predictions,
)

# Skip all tests if himalaya is not installed
himalaya = pytest.importorskip("himalaya")


# ─── Fixtures ────────────────────────────────────────────────


@pytest.fixture
def delayed_prepared_data():
    """PreparedData with delays already applied (default preprocessor)."""
    rng = np.random.RandomState(42)
    n_features_raw = 4  # 2 groups: [1, 3] dims
    n_voxels = 5
    delays = [1, 2]
    n_delayed = n_features_raw * len(delays)
    n_train, n_test = 80, 20

    true_weights = rng.randn(n_delayed, n_voxels).astype(np.float32)
    X_train = rng.randn(n_train, n_delayed).astype(np.float32)
    Y_train = X_train @ true_weights + rng.randn(n_train, n_voxels).astype(np.float32) * 0.1
    X_test = rng.randn(n_test, n_delayed).astype(np.float32)
    Y_test = X_test @ true_weights + rng.randn(n_test, n_voxels).astype(np.float32) * 0.1

    return PreparedData(
        X_train=X_train, Y_train=Y_train,
        X_test=X_test, Y_test=Y_test,
        feature_names=["intercept", "embedding"],
        feature_dims=[1, 3],
        delays=delays,
        train_runs=["s1", "s2"],
        test_runs=["s3"],
        metadata={'delays_applied': True},
    )


@pytest.fixture
def undelayed_prepared_data():
    """PreparedData with delays NOT applied (apply_delays: false)."""
    rng = np.random.RandomState(42)
    n_features_raw = 4  # 2 groups: [1, 3] dims
    n_voxels = 5
    delays = [1, 2]
    n_train, n_test = 80, 20

    true_weights = rng.randn(n_features_raw, n_voxels).astype(np.float32)
    X_train = rng.randn(n_train, n_features_raw).astype(np.float32)
    Y_train = X_train @ true_weights + rng.randn(n_train, n_voxels).astype(np.float32) * 0.1
    X_test = rng.randn(n_test, n_features_raw).astype(np.float32)
    Y_test = X_test @ true_weights + rng.randn(n_test, n_voxels).astype(np.float32) * 0.1

    return PreparedData(
        X_train=X_train, Y_train=Y_train,
        X_test=X_test, Y_test=Y_test,
        feature_names=["intercept", "embedding"],
        feature_dims=[1, 3],
        delays=delays,
        train_runs=["s1", "s2"],
        test_runs=["s3"],
        metadata={'delays_applied': False},
    )


# ─── Helper tests ────────────────────────────────────────────


class TestResolveAlphas:
    def test_logspace_string(self):
        alphas = _resolve_alphas("logspace(-2,5,20)")
        assert len(alphas) == 20
        np.testing.assert_allclose(alphas[0], 0.01, rtol=1e-5)
        np.testing.assert_allclose(alphas[-1], 1e5, rtol=1e-5)

    def test_list_input(self):
        alphas = _resolve_alphas([1, 10, 100])
        assert len(alphas) == 3
        np.testing.assert_array_equal(alphas, [1, 10, 100])


class TestComputeGroupLabels:
    def test_delayed(self):
        labels = _compute_group_labels([1, 985], [1, 2, 3, 4], delays_applied=True)
        assert len(labels) == (1 + 985) * 4
        assert labels[:4] == [0, 0, 0, 0]
        assert labels[4:8] == [1, 1, 1, 1]

    def test_undelayed(self):
        labels = _compute_group_labels([1, 985], [1, 2, 3, 4], delays_applied=False)
        assert len(labels) == 1 + 985
        assert labels[0] == 0
        assert all(l == 1 for l in labels[1:])


class TestComputeGroupSlices:
    def test_delayed(self):
        slices = _compute_group_slices([1, 3], delays_applied=True, delays=[1, 2])
        assert slices[0] == slice(0, 2)   # 1 dim * 2 delays
        assert slices[1] == slice(2, 8)   # 3 dims * 2 delays

    def test_undelayed(self):
        slices = _compute_group_slices([1, 3], delays_applied=False)
        assert slices[0] == slice(0, 1)
        assert slices[1] == slice(1, 4)


class TestScorePredictions:
    def test_r2_perfect(self):
        Y = np.random.RandomState(0).randn(50, 3)
        scores = _score_predictions(Y, Y, metric='r2')
        np.testing.assert_allclose(scores, 1.0, atol=1e-10)

    def test_pearson_r_perfect(self):
        Y = np.random.RandomState(0).randn(50, 3)
        scores = _score_predictions(Y, Y, metric='pearson_r')
        np.testing.assert_allclose(scores, 1.0, atol=1e-10)

    def test_r2_uncorrelated(self):
        rng = np.random.RandomState(0)
        Y_pred = rng.randn(200, 3)
        Y_true = rng.randn(200, 3)
        scores = _score_predictions(Y_pred, Y_true, metric='r2')
        assert all(s < 0.2 for s in scores)

    def test_unknown_metric(self):
        Y = np.ones((5, 2))
        with pytest.raises(ValueError, match="Unknown metric"):
            _score_predictions(Y, Y, metric='mse')


class TestDelayer:
    def test_transform_shape(self):
        X = np.random.randn(20, 3)
        delayer = _Delayer(delays=[0, 1, 2])
        X_delayed = delayer.fit_transform(X)
        assert X_delayed.shape == (20, 9)

    def test_identity_delay(self):
        X = np.random.randn(20, 3)
        delayer = _Delayer(delays=[0])
        X_delayed = delayer.fit_transform(X)
        np.testing.assert_array_equal(X_delayed, X)


# ─── HimalayaRidgeModel tests ───────────────────────────────


class TestHimalayaRidgeModel:
    def test_fit_returns_model_result(self, delayed_prepared_data):
        model = HimalayaRidgeModel()
        config = {
            "model": {
                "params": {
                    "alphas": "logspace(0,3,5)",
                    "cv": 3,
                },
            },
        }
        result = model.fit(delayed_prepared_data, config)
        assert isinstance(result, ModelResult)

    def test_output_shapes(self, delayed_prepared_data):
        model = HimalayaRidgeModel()
        config = {"model": {"params": {"alphas": "logspace(0,3,3)", "cv": 3}}}
        result = model.fit(delayed_prepared_data, config)
        n_delayed = delayed_prepared_data.X_train.shape[1]
        n_voxels = delayed_prepared_data.Y_train.shape[1]
        assert result.weights.shape == (n_delayed, n_voxels)
        assert result.scores.shape == (n_voxels,)
        assert result.alphas.shape == (n_voxels,)

    def test_metadata_propagated(self, delayed_prepared_data):
        model = HimalayaRidgeModel()
        config = {"model": {"params": {"cv": 3}}}
        result = model.fit(delayed_prepared_data, config)
        assert result.feature_names == delayed_prepared_data.feature_names
        assert result.delays == delayed_prepared_data.delays

    def test_validate_config_bad_cv(self):
        model = HimalayaRidgeModel()
        errors = model.validate_config({"model": {"params": {"cv": 1}}})
        assert any("cv" in e for e in errors)

    def test_validate_config_valid(self):
        model = HimalayaRidgeModel()
        errors = model.validate_config({"model": {"params": {"cv": 5}}})
        assert errors == []


# ─── BandedRidgeModel tests ─────────────────────────────────


class TestBandedRidgeModel:
    def test_fit_returns_model_result(self, delayed_prepared_data):
        model = BandedRidgeModel()
        config = {
            "model": {
                "params": {
                    "alphas": "logspace(0,3,5)",
                    "cv": 3,
                    "solver_params": {"n_iter": 5},
                },
            },
        }
        result = model.fit(delayed_prepared_data, config)
        assert isinstance(result, ModelResult)

    def test_output_shapes(self, delayed_prepared_data):
        model = BandedRidgeModel()
        config = {
            "model": {
                "params": {
                    "alphas": "logspace(0,3,3)",
                    "cv": 3,
                    "solver_params": {"n_iter": 5},
                },
            },
        }
        result = model.fit(delayed_prepared_data, config)
        n_delayed = delayed_prepared_data.X_train.shape[1]
        n_voxels = delayed_prepared_data.Y_train.shape[1]
        assert result.weights.shape == (n_delayed, n_voxels)
        assert result.scores.shape == (n_voxels,)

    def test_metadata_has_deltas(self, delayed_prepared_data):
        model = BandedRidgeModel()
        config = {
            "model": {
                "params": {
                    "cv": 3,
                    "solver_params": {"n_iter": 5},
                },
            },
        }
        result = model.fit(delayed_prepared_data, config)
        assert 'deltas' in result.metadata
        assert 'groups' in result.metadata

    def test_validate_config_bad_cv(self):
        model = BandedRidgeModel()
        errors = model.validate_config({"model": {"params": {"cv": 0}}})
        assert any("cv" in e for e in errors)


# ─── MultipleKernelRidgeModel tests ─────────────────────────


class TestMultipleKernelRidgeModel:
    def test_fit_returns_model_result(self, undelayed_prepared_data):
        model = MultipleKernelRidgeModel()
        config = {
            "preprocessing": {"apply_delays": False},
            "model": {
                "params": {
                    "alphas": "logspace(0,3,3)",
                    "cv": 3,
                    "n_iter": 5,
                },
            },
        }
        result = model.fit(undelayed_prepared_data, config)
        assert isinstance(result, ModelResult)

    def test_output_shapes(self, undelayed_prepared_data):
        model = MultipleKernelRidgeModel()
        config = {
            "preprocessing": {"apply_delays": False},
            "model": {
                "params": {
                    "alphas": "logspace(0,3,3)",
                    "cv": 3,
                    "n_iter": 5,
                },
            },
        }
        result = model.fit(undelayed_prepared_data, config)
        n_train = undelayed_prepared_data.X_train.shape[0]
        n_voxels = undelayed_prepared_data.Y_train.shape[1]
        # dual_coef_ has shape (n_samples, n_targets)
        assert result.weights.shape == (n_train, n_voxels)
        assert result.scores.shape == (n_voxels,)

    def test_metadata_has_deltas_and_is_dual(self, undelayed_prepared_data):
        model = MultipleKernelRidgeModel()
        config = {
            "preprocessing": {"apply_delays": False},
            "model": {
                "params": {"cv": 3, "n_iter": 5},
            },
        }
        result = model.fit(undelayed_prepared_data, config)
        assert result.metadata.get('is_dual') is True
        assert 'deltas' in result.metadata

    def test_validate_config_requires_no_delays(self):
        model = MultipleKernelRidgeModel()
        # apply_delays defaults to True -> should error
        errors = model.validate_config({"model": {"params": {}}})
        assert any("apply_delays" in e for e in errors)

    def test_validate_config_ok_with_no_delays(self):
        model = MultipleKernelRidgeModel()
        errors = model.validate_config({
            "preprocessing": {"apply_delays": False},
            "model": {"params": {}},
        })
        delay_errors = [e for e in errors if "apply_delays" in e]
        assert delay_errors == []
