"""Tests for bootstrap ridge regression."""

import numpy as np
import pytest

from fmriflow.core.ridge import _columnwise_corr, bootstrap_ridge


class TestBootstrapRidge:
    @pytest.fixture
    def linear_data(self):
        """Create simple linear data: Y = X @ true_weights + noise."""
        rng = np.random.RandomState(42)
        n_train, n_test, n_features, n_voxels = 200, 50, 5, 3
        true_weights = rng.randn(n_features, n_voxels).astype(np.float32)

        X_train = rng.randn(n_train, n_features).astype(np.float32)
        noise_train = rng.randn(n_train, n_voxels).astype(np.float32) * 0.1
        Y_train = X_train @ true_weights + noise_train

        X_test = rng.randn(n_test, n_features).astype(np.float32)
        noise_test = rng.randn(n_test, n_voxels).astype(np.float32) * 0.1
        Y_test = X_test @ true_weights + noise_test

        return X_train, Y_train, X_test, Y_test, true_weights

    def test_recovered_weights_correlate(self, linear_data):
        X_train, Y_train, X_test, Y_test, true_weights = linear_data
        alphas = np.logspace(-2, 2, 5)

        weights, scores, best_alphas, _, _ = bootstrap_ridge(
            X_train, Y_train, X_test, Y_test, alphas,
            nboots=3, chunklen=20, nchunks=2,
        )

        # Recovered weights should correlate with true weights
        for v in range(true_weights.shape[1]):
            corr = np.corrcoef(weights[:, v], true_weights[:, v])[0, 1]
            assert corr > 0.5, f"Voxel {v} correlation too low: {corr}"

    def test_output_shapes(self, linear_data):
        X_train, Y_train, X_test, Y_test, _ = linear_data
        n_features = X_train.shape[1]
        n_voxels = Y_train.shape[1]
        alphas = np.logspace(0, 2, 3)

        weights, scores, best_alphas, boot_corrs, valinds = bootstrap_ridge(
            X_train, Y_train, X_test, Y_test, alphas,
            nboots=2, chunklen=20, nchunks=2,
        )

        assert weights.shape == (n_features, n_voxels)
        assert scores.shape == (n_voxels,)
        assert best_alphas.shape == (n_voxels,)
        assert boot_corrs.shape == (len(alphas), n_voxels, 2)

    def test_single_alpha_mode(self, linear_data):
        X_train, Y_train, X_test, Y_test, _ = linear_data
        alphas = np.logspace(0, 2, 3)

        _, _, best_alphas, _, _ = bootstrap_ridge(
            X_train, Y_train, X_test, Y_test, alphas,
            nboots=2, chunklen=20, nchunks=2,
            single_alpha=True,
        )

        # All voxels should have the same alpha
        assert len(np.unique(best_alphas)) == 1

    def test_scores_are_finite(self, linear_data):
        X_train, Y_train, X_test, Y_test, _ = linear_data
        alphas = np.logspace(0, 2, 3)

        _, scores, _, _, _ = bootstrap_ridge(
            X_train, Y_train, X_test, Y_test, alphas,
            nboots=2, chunklen=20, nchunks=2,
        )

        assert np.isfinite(scores).all()


class TestColumnwiseCorr:
    def test_against_numpy(self):
        rng = np.random.RandomState(0)
        a = rng.randn(100, 5)
        b = rng.randn(100, 5)
        corrs = _columnwise_corr(a, b)
        for i in range(5):
            expected = np.corrcoef(a[:, i], b[:, i])[0, 1]
            np.testing.assert_allclose(corrs[i], expected, atol=1e-5)

    def test_perfect_correlation(self):
        a = np.arange(50, dtype=float).reshape(50, 1)
        corrs = _columnwise_corr(a, a)
        np.testing.assert_allclose(corrs, [1.0], atol=1e-5)

    def test_output_shape(self):
        a = np.random.randn(30, 7)
        b = np.random.randn(30, 7)
        corrs = _columnwise_corr(a, b)
        assert corrs.shape == (7,)
