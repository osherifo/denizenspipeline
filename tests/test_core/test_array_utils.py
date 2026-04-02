"""Tests for array utility functions."""

import numpy as np
import pytest

from fmriflow.core.array_utils import (
    make_delayed,
    mean_center,
    undelay_weights,
    zscore,
)


class TestZscore:
    def test_basic_normalization(self):
        a = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])
        z = zscore(a)
        # Each column should have approximately zero mean and unit std
        np.testing.assert_allclose(z.mean(axis=0), 0, atol=1e-6)
        np.testing.assert_allclose(z.std(axis=0), 1, atol=1e-3)

    def test_precomputed_mean_std(self):
        a = np.array([[1.0, 2.0], [3.0, 4.0]])
        m = np.array([2.0, 3.0])
        s = np.array([1.0, 1.0])
        z = zscore(a, mean=m, std=s)
        expected = np.array([[-1.0, -1.0], [1.0, 1.0]])
        np.testing.assert_allclose(z, expected, atol=1e-6)

    def test_return_info(self):
        a = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])
        z, m, s = zscore(a, return_info=True)
        np.testing.assert_allclose(m, [3.0, 4.0])
        assert z.shape == a.shape

    def test_nan_handling(self):
        a = np.array([[1.0, np.nan], [3.0, 4.0], [5.0, 6.0]])
        z = zscore(a)
        assert z.shape == a.shape
        # Column 0 should be valid
        assert np.isfinite(z[:, 0]).all()

    def test_all_zeros_column(self):
        a = np.array([[0.0, 1.0], [0.0, 2.0], [0.0, 3.0]])
        z = zscore(a)
        # Zero-std column should not produce inf/nan (EPSILON guards)
        assert np.isfinite(z).all()
        # All zeros column stays near zero
        np.testing.assert_allclose(z[:, 0], 0, atol=1e-3)

    def test_2d_output_shape(self):
        a = np.random.randn(100, 10)
        z = zscore(a)
        assert z.shape == (100, 10)


class TestMeanCenter:
    def test_basic(self):
        a = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])
        centered, m = mean_center(a)
        np.testing.assert_allclose(centered.mean(axis=0), 0, atol=1e-6)
        np.testing.assert_allclose(m, [3.0, 4.0])

    def test_precomputed_mean(self):
        a = np.array([[1.0, 2.0], [3.0, 4.0]])
        m = np.array([1.0, 1.0])
        centered, m_out = mean_center(a, mean=m)
        expected = np.array([[0.0, 1.0], [2.0, 3.0]])
        np.testing.assert_allclose(centered, expected)
        np.testing.assert_allclose(m_out, m)


class TestMakeDelayed:
    def test_zero_delay_identity(self):
        stim = np.eye(5)
        delayed = make_delayed(stim, [0])
        np.testing.assert_array_equal(delayed, stim)

    def test_positive_delay_shifts_down(self):
        stim = np.arange(10).reshape(5, 2).astype(float)
        delayed = make_delayed(stim, [1])
        # First row should be zero (shifted down by 1)
        np.testing.assert_array_equal(delayed[0], [0, 0])
        # Second row should be original first row
        np.testing.assert_array_equal(delayed[1], stim[0])

    def test_negative_delay_shifts_up(self):
        stim = np.arange(10).reshape(5, 2).astype(float)
        delayed = make_delayed(stim, [-1])
        # First row should be original second row
        np.testing.assert_array_equal(delayed[0], stim[1])
        # Last row should be zero
        np.testing.assert_array_equal(delayed[-1], [0, 0])

    def test_circpad(self):
        stim = np.arange(10).reshape(5, 2).astype(float)
        delayed = make_delayed(stim, [1], circpad=True)
        # First row should wrap around to last row of original
        np.testing.assert_array_equal(delayed[0], stim[-1])

    def test_output_shape(self):
        n_trs, n_dims = 30, 4
        delays = [0, 1, 2, 3]
        stim = np.random.randn(n_trs, n_dims)
        delayed = make_delayed(stim, delays)
        assert delayed.shape == (n_trs, n_dims * len(delays))

    def test_multiple_delays(self):
        stim = np.array([[1.0, 0.0], [0.0, 1.0], [0.0, 0.0], [0.0, 0.0]])
        delayed = make_delayed(stim, [0, 1])
        assert delayed.shape == (4, 4)
        # delay=0 part should be identity
        np.testing.assert_array_equal(delayed[:, :2], stim)
        # delay=1 part, first row should be zero
        np.testing.assert_array_equal(delayed[0, 2:], [0, 0])
        np.testing.assert_array_equal(delayed[1, 2:], stim[0])


class TestUndelayWeights:
    def test_reshape_correctness(self):
        n_delays = 4
        n_features = 3
        n_voxels = 5
        weights = np.random.randn(n_features * n_delays, n_voxels)
        undelayed = undelay_weights(weights, list(range(n_delays)))
        assert undelayed.shape == (n_delays, n_features, n_voxels)

    def test_roundtrip_with_make_delayed(self):
        n_trs, n_features, n_voxels = 20, 3, 5
        delays = [0, 1, 2]
        # Create a simple weight matrix
        true_weights = np.random.randn(n_features, n_voxels)
        # Tile for each delay
        delayed_weights = np.tile(true_weights, (len(delays), 1))
        undelayed = undelay_weights(delayed_weights, delays)
        # Each delay slice should match the original weights
        for d in range(len(delays)):
            np.testing.assert_array_equal(undelayed[d], true_weights)

    def test_1d_input(self):
        weights_1d = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
        undelayed = undelay_weights(weights_1d, [0, 1])
        assert undelayed.shape == (2, 3, 1)
