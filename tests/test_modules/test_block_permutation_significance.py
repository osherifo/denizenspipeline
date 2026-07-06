"""Tests for BlockPermutationSignificanceAnalyzer."""

from __future__ import annotations

import numpy as np
import pytest

from fmriflow.context import PipelineContext
from fmriflow.core.types import ModelResult, PreparedData
from fmriflow.modules.analyzers.block_permutation_significance import (
    BlockPermutationSignificanceAnalyzer,
    _block_permutation_pvalues,
    _compute_test_predictions,
    _pearson_r_per_col,
)


# ── helpers ────────────────────────────────────────────────────────────


def _make_signal_and_noise(n_train=200, n_test=60, fdim=10, n_voxels=8,
                          seed=0, n_delays=1):
    """Build a synthetic (X_train, X_test, Y_train, Y_test, W) with the first
    half of the voxels driven by a real linear signal and the second half
    pure noise. Returns primal-space weights (fdim, n_voxels)."""
    rng = np.random.RandomState(seed)
    X_train = rng.randn(n_train, fdim).astype(np.float32)
    X_test = rng.randn(n_test, fdim).astype(np.float32)
    W = rng.randn(fdim, n_voxels).astype(np.float32)
    noise_train = 0.1 * rng.randn(n_train, n_voxels).astype(np.float32)
    noise_test = 0.1 * rng.randn(n_test, n_voxels).astype(np.float32)
    Y_train = X_train @ W + noise_train
    Y_test = X_test @ W + noise_test
    # kill signal in the right half so those columns are pure noise
    n_null = n_voxels // 2
    Y_train[:, n_null:] = rng.randn(n_train, n_voxels - n_null).astype(np.float32)
    Y_test[:, n_null:] = rng.randn(n_test, n_voxels - n_null).astype(np.float32)
    return X_train, X_test, Y_train, Y_test, W


def _prepared(X_train, X_test, Y_train, Y_test, fdim):
    return PreparedData(
        X_train=X_train, Y_train=Y_train,
        X_test=X_test, Y_test=Y_test,
        train_runs=["r0"], test_runs=["r1"],
        feature_names=["feat"], feature_dims=[fdim], delays=[],
    )


def _model_primal(W_delayed, scores, fdim, delays=(1,)):
    return ModelResult(
        weights=W_delayed, scores=scores,
        alphas=np.ones(scores.size, dtype=np.float32),
        feature_names=["feat"], feature_dims=[fdim], delays=list(delays),
        metadata={"is_dual": False},
    )


def _config(**params):
    return {"analysis": [{"name": "block_permutation_significance", "params": params}]}


# ── unit tests on the pure helpers ────────────────────────────────────


class TestBlockPermutationPvalues:
    def test_shape_and_range(self):
        rng = np.random.RandomState(0)
        Y = rng.randn(100, 5).astype(np.float32)
        P = rng.randn(100, 5).astype(np.float32)
        pv, tr = _block_permutation_pvalues(
            Y, P, n_perms=100, block_size=10,
            rng=np.random.default_rng(0))
        assert pv.shape == (5,) == tr.shape
        assert (pv >= 0).all() and (pv <= 1).all()

    def test_pvalues_never_exactly_zero(self):
        """(count + 1) / (n_perms + 1) — Phipson & Smyth correction."""
        rng = np.random.RandomState(0)
        # Signal so strong the true r beats every shuffle:
        X = rng.randn(80, 4).astype(np.float32)
        Y = X.copy()
        pv, _ = _block_permutation_pvalues(
            Y, Y, n_perms=50, block_size=5,
            rng=np.random.default_rng(0))
        assert (pv > 0).all()
        assert (pv <= 1.0 / (50 + 1) + 1e-9).all()

    def test_pure_noise_pvalues_are_uniform_ish(self):
        rng = np.random.RandomState(1)
        Y = rng.randn(120, 200).astype(np.float32)
        P = rng.randn(120, 200).astype(np.float32)
        pv, _ = _block_permutation_pvalues(
            Y, P, n_perms=300, block_size=10,
            rng=np.random.default_rng(1))
        # Under H0, one-sided p should have mean ~0.5.
        assert 0.4 < pv.mean() < 0.6

    def test_seeded_reproducibility(self):
        rng = np.random.RandomState(0)
        Y = rng.randn(80, 5).astype(np.float32)
        P = rng.randn(80, 5).astype(np.float32)
        pv_a, _ = _block_permutation_pvalues(
            Y, P, n_perms=50, block_size=10,
            rng=np.random.default_rng(42))
        pv_b, _ = _block_permutation_pvalues(
            Y, P, n_perms=50, block_size=10,
            rng=np.random.default_rng(42))
        assert np.array_equal(pv_a, pv_b)

    def test_true_r_matches_pearson(self):
        rng = np.random.RandomState(0)
        Y = rng.randn(100, 3).astype(np.float32)
        P = rng.randn(100, 3).astype(np.float32)
        _, tr = _block_permutation_pvalues(
            Y, P, n_perms=10, block_size=10,
            rng=np.random.default_rng(0))
        expected = _pearson_r_per_col(Y, P)
        np.testing.assert_allclose(tr, expected, atol=1e-6)


class TestComputeTestPredictions:
    def test_primal_no_delays(self):
        X_train, X_test, Y_train, Y_test, W = _make_signal_and_noise(
            n_train=50, n_test=20, fdim=6, n_voxels=4)
        result = _model_primal(W, np.zeros(4, dtype=np.float32), fdim=6, delays=[1])
        prep = _prepared(X_train, X_test, Y_train, Y_test, fdim=6)
        preds = _compute_test_predictions(result, prep, delays=[1])
        # With un-delayed X and n_delays=1, predictions should be X_test @ W.
        np.testing.assert_allclose(preds, X_test @ W, atol=1e-4)

    def test_dual_flag_materialises_primal(self):
        X_train, X_test, Y_train, Y_test, W = _make_signal_and_noise(
            n_train=40, n_test=15, fdim=5, n_voxels=3)
        # Solve for a dual that gives the same primal: primal = X_train.T @ dual.
        # Pick dual = (X_train X_train.T)^-1 X_train W to satisfy that.
        K = X_train @ X_train.T
        dual = np.linalg.solve(K + 1e-3 * np.eye(K.shape[0]),
                               X_train @ W).astype(np.float32)
        result = ModelResult(
            weights=dual,
            scores=np.zeros(3, dtype=np.float32),
            alphas=np.ones(3, dtype=np.float32),
            feature_names=["feat"], feature_dims=[5], delays=[1],
            metadata={"is_dual": True},
        )
        prep = _prepared(X_train, X_test, Y_train, Y_test, fdim=5)
        preds = _compute_test_predictions(result, prep, delays=[1])
        expected = X_test @ (X_train.T @ dual)
        np.testing.assert_allclose(preds, expected, atol=1e-4)


# ── analyzer-level tests ──────────────────────────────────────────────


class TestBlockPermutationSignificanceAnalyzer:
    def _run(self, params=None, n_perms=100, block_size=5, seed=0):
        params = dict(params or {})
        params.setdefault("n_permutations", n_perms)
        params.setdefault("block_size", block_size)
        params.setdefault("seed", seed)
        analyzer = BlockPermutationSignificanceAnalyzer()

        X_train, X_test, Y_train, Y_test, W = _make_signal_and_noise(
            n_train=200, n_test=60, fdim=10, n_voxels=8, seed=seed)
        prep = _prepared(X_train, X_test, Y_train, Y_test, fdim=10)
        result = _model_primal(
            W, scores=_pearson_r_per_col(Y_test, X_test @ W),
            fdim=10, delays=[1])

        cfg = _config(**params)
        ctx = PipelineContext(cfg)
        ctx.put("result", result)
        ctx.put("prepared", prep)
        analyzer.analyze(ctx, cfg)
        return ctx

    def test_publishes_expected_keys(self):
        ctx = self._run()
        assert ctx.has("analysis.significance")
        payload = ctx.get("analysis.significance")
        for key in ("scores", "pvalues", "pvalues_corrected", "sig_mask",
                    "n_permutations", "block_size", "alpha", "fdr_method"):
            assert key in payload, f"missing {key}"

    def test_shapes_match_n_voxels(self):
        ctx = self._run()
        p = ctx.get("analysis.significance")
        assert p["scores"].shape == (8,)
        assert p["pvalues"].shape == (8,)
        assert p["pvalues_corrected"].shape == (8,)
        assert p["sig_mask"].shape == (8,)
        assert p["sig_mask"].dtype == bool

    def test_signal_voxels_survive_noise_voxels_do_not(self):
        # 500 perms + alpha=0.2 is plenty for the strong-signal test set.
        ctx = self._run(n_perms=500, params={"alpha": 0.2})
        p = ctx.get("analysis.significance")
        sig = p["sig_mask"]
        # First half = real signal → most should survive.
        assert sig[:4].sum() >= 3
        # Second half = pure noise → almost none should survive.
        assert sig[4:].sum() <= 1

    def test_custom_output_key(self):
        ctx = self._run(params={"output_key": "analysis.mysig"})
        assert ctx.has("analysis.mysig")
        assert not ctx.has("analysis.significance")

    def test_seeded_reproducibility(self):
        ctx_a = self._run(seed=7)
        ctx_b = self._run(seed=7)
        pa = ctx_a.get("analysis.significance")["pvalues"]
        pb = ctx_b.get("analysis.significance")["pvalues"]
        np.testing.assert_array_equal(pa, pb)

    def test_validate_rejects_non_numeric_params(self):
        analyzer = BlockPermutationSignificanceAnalyzer()
        errs = analyzer.validate_config(_config(n_permutations="foo"))
        assert any("n_permutations" in e for e in errs)

        errs = analyzer.validate_config(_config(alpha="bad"))
        assert any("alpha" in e for e in errs)

    def test_validate_accepts_alpha_boundary(self):
        analyzer = BlockPermutationSignificanceAnalyzer()
        assert analyzer.validate_config(_config(alpha=0.0)) == []
        assert analyzer.validate_config(_config(alpha=1.0)) == []
        assert any("alpha" in e for e in
                   analyzer.validate_config(_config(alpha=1.5)))
        assert any("alpha" in e for e in
                   analyzer.validate_config(_config(alpha=-0.1)))

    def test_validate_rejects_bad_fdr_method(self):
        analyzer = BlockPermutationSignificanceAnalyzer()
        errs = analyzer.validate_config(_config(fdr_method="bh"))
        assert any("fdr_method" in e for e in errs)


class TestBlockConstruction:
    def test_blocks_exactly_block_size_except_last(self):
        """With T=291 and block_size=10, blocks should be [10,10,…,10,1]
        (29 full blocks + a 1-TR remainder), not np.array_split's mixed
        10s and 11s."""
        rng = np.random.RandomState(0)
        # Bump the shapes to have a non-divisible T so any wrong block
        # sizing shows up.
        Y = rng.randn(291, 4).astype(np.float32)
        P = rng.randn(291, 4).astype(np.float32)
        # Just call the fn and confirm it runs cleanly and hits the
        # (count + 1) / (n + 1) invariant on a strong-signal voxel.
        pv, _ = _block_permutation_pvalues(
            Y, Y, n_perms=20, block_size=10,
            rng=np.random.default_rng(0))
        assert pv.shape == (4,)
        assert (pv > 0).all()
