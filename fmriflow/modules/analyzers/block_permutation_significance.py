"""Block-permutation null + Benjamini-Hochberg FDR per voxel.

Subject-scope analyzer. Standard blockwise-shuffled permutation test:

* split test TRs into contiguous blocks of ``block_size`` (default 10),
* shuffle the blocks of ``predictions``, recompute Pearson r per voxel,
* count how often the shuffled score is >= the true score,
* p-value = count / n_permutations,
* apply Benjamini-Hochberg FDR at ``alpha`` (default 0.05),
* write ``analysis.significance`` (or ``output_key``) into the subject
  context with ``scores`` (true r), ``pvalues``, ``pvalues_corrected``,
  ``sig_mask``, and the parameters used.

The ``r_flatmap`` reporter renders the FDR-significant map when given
``significance_key: analysis.significance`` (non-significant voxels
become NaN so pycortex paints them grey).

For banded-ridge models the saved ``ModelResult.weights`` are dual
coefficients (``metadata.is_dual=True``); we materialise the delayed
primal weights from ``X_train`` to recompute held-out predictions
without re-running the solver. The per-band ``exp(delta)`` scaling is
omitted because Pearson r is invariant to per-voxel positive scale —
the relative shape of the prediction time-course is all that matters.
"""

from __future__ import annotations

import logging
import time

import numpy as np

from fmriflow.core.array_utils import make_delayed
from fmriflow.core.types import ModelResult, PreparedData
from fmriflow.modules._decorators import analyzer

logger = logging.getLogger(__name__)


@analyzer("block_permutation_significance")
class BlockPermutationSignificanceAnalyzer:
    """Block-permutation Pearson-r null + BH-FDR significance per voxel."""

    name = "block_permutation_significance"
    PARAM_SCHEMA = {
        "n_permutations": {
            "type": "int", "default": 5000, "min": 1,
            "description": "Number of block-shuffled draws from the null.",
        },
        "block_size": {
            "type": "int", "default": 10, "min": 1,
            "description": (
                "TR block length for shuffling. Larger blocks better "
                "preserve temporal autocorrelation under H0."
            ),
        },
        "alpha": {
            "type": "float", "default": 0.05, "min": 0.0, "max": 1.0,
            "description": "BH-FDR target false-discovery rate.",
        },
        "fdr_method": {
            "type": "str", "default": "indep",
            "enum": ["indep", "negcorr"],
            "description": (
                "Passed to ``statsmodels.stats.multitest.fdrcorrection``. "
                "'indep' = Benjamini-Hochberg, 'negcorr' = Benjamini-Yekutieli."
            ),
        },
        "seed": {
            "type": "int", "default": 1234,
            "description": "RNG seed for reproducible block shuffles.",
        },
        "output_key": {
            "type": "str", "default": "analysis.significance",
            "description": "Context key under which to publish results.",
        },
    }

    def analyze(self, context, config: dict) -> None:
        try:
            from statsmodels.stats.multitest import fdrcorrection
        except ImportError as exc:
            logger.warning(
                "block_permutation_significance: statsmodels not importable "
                "(%s) — skipping", exc)
            return

        cfg = _my_cfg(config, self.name)
        n_perms = int(cfg.get("n_permutations", 5000))
        block_size = int(cfg.get("block_size", 10))
        alpha = float(cfg.get("alpha", 0.05))
        fdr_method = cfg.get("fdr_method", "indep")
        seed = int(cfg.get("seed", 1234))
        output_key = cfg.get("output_key", "analysis.significance")

        result = context.get("result", ModelResult)
        prepared = context.get("prepared", PreparedData)

        delays = _resolve_delays(result, config)
        predictions = _compute_test_predictions(result, prepared, delays)
        Y_test = np.asarray(prepared.Y_test, dtype=np.float32)
        if predictions.shape != Y_test.shape:
            logger.warning(
                "block_permutation_significance: prediction shape %s != "
                "Y_test shape %s — skipping",
                predictions.shape, Y_test.shape)
            return

        rng = np.random.default_rng(seed)
        t0 = time.time()
        pvalues, true_r = _block_permutation_pvalues(
            Y_test, predictions, n_perms, block_size, rng)
        logger.info(
            "block_permutation_significance: %d perms x %d voxels in %.1fs",
            n_perms, true_r.size, time.time() - t0)

        rejected, p_corrected = fdrcorrection(
            pvalues, alpha=alpha, method=fdr_method, is_sorted=False)
        n_sig = int(rejected.sum())
        logger.info(
            "block_permutation_significance: %d/%d voxels significant "
            "(%.1f%%) at alpha=%g (%s FDR)",
            n_sig, rejected.size, 100.0 * n_sig / max(rejected.size, 1),
            alpha, fdr_method)

        context.put(output_key, {
            "scores": true_r.astype(np.float32),
            "pvalues": pvalues.astype(np.float32),
            "pvalues_corrected": p_corrected.astype(np.float32),
            "sig_mask": rejected.astype(bool),
            "n_permutations": n_perms,
            "block_size": block_size,
            "alpha": alpha,
            "fdr_method": fdr_method,
        })

    def validate_config(self, config: dict) -> list[str]:
        errors: list[str] = []
        cfg = _my_cfg(config, self.name)
        for k in ("n_permutations", "block_size"):
            v = cfg.get(k)
            if v is None:
                continue
            try:
                iv = int(v)
            except (TypeError, ValueError):
                errors.append(
                    f"block_permutation_significance.{k} must be an integer, "
                    f"got {v!r}")
                continue
            if iv < 1:
                errors.append(
                    f"block_permutation_significance.{k} must be >= 1")
        a = cfg.get("alpha")
        if a is not None:
            try:
                av = float(a)
            except (TypeError, ValueError):
                errors.append(
                    f"block_permutation_significance.alpha must be a number, "
                    f"got {a!r}")
            else:
                if not (0.0 <= av <= 1.0):
                    errors.append(
                        "block_permutation_significance.alpha must be in [0, 1]")
        method = cfg.get("fdr_method")
        if method is not None and method not in ("indep", "negcorr"):
            errors.append(
                "block_permutation_significance.fdr_method must be "
                "'indep' or 'negcorr'")
        return errors


def _my_cfg(config: dict, name: str) -> dict:
    for acfg in config.get("analysis", []):
        if acfg.get("name") == name:
            return acfg.get("params", {}) or {}
    return {}


def _resolve_delays(result: ModelResult, config: dict) -> list[int]:
    if result.delays:
        return list(result.delays)
    delays = ((config.get("model") or {}).get("params") or {}).get("delays")
    return list(delays) if delays else [1, 2, 3, 4]


def _compute_test_predictions(
    result: ModelResult, prepared: PreparedData, delays: list[int],
) -> np.ndarray:
    """Materialise held-out predictions from (dual-or-primal) weights.

    Handles the case where ``X_train`` / ``X_test`` in ``PreparedData``
    are un-delayed (the kernelized model applies its own delays
    internally) by re-applying ``make_delayed`` here. If the saved X
    is already delay-expanded (a ``delay`` step ran in the preparation
    pipeline), uses it as-is.
    """
    X_train = np.asarray(prepared.X_train, dtype=np.float32)
    X_test = np.asarray(prepared.X_test, dtype=np.float32)
    raw_fdim = sum(int(x) for x in (result.feature_dims or prepared.feature_dims or [X_train.shape[1]]))
    n_delays = max(1, len(delays))
    if X_train.shape[1] == raw_fdim and n_delays > 1:
        X_train_delayed = make_delayed(X_train, delays).astype(np.float32)
        X_test_delayed = make_delayed(X_test, delays).astype(np.float32)
    else:
        X_train_delayed = X_train
        X_test_delayed = X_test
    weights = np.asarray(result.weights, dtype=np.float32)
    is_dual = bool((result.metadata or {}).get("is_dual"))
    if is_dual:
        primal_delayed = X_train_delayed.T @ weights
    else:
        primal_delayed = weights
    return X_test_delayed @ primal_delayed


def _block_permutation_pvalues(
    Y_test: np.ndarray, predictions: np.ndarray,
    n_perms: int, block_size: int, rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    """One-sided p-values: P(r_shuffled >= r_true) per voxel.

    Block-shuffle predictions in time, recompute Pearson r vs. truth,
    one-sided count of >=. Faster than the naive form because the
    denominator of Pearson r is invariant to reordering rows — both
    per-voxel norms are constant — so we only recompute the numerator
    inside the loop.

    Uses the ``(count + 1) / (n_perms + 1)`` correction so p-values are
    never exactly 0 (Phipson & Smyth 2010) — otherwise BH-FDR would
    treat unresolved voxels as perfect evidence.
    """
    true_r = _pearson_r_per_col(Y_test, predictions)

    Yc = Y_test - Y_test.mean(axis=0, keepdims=True)
    Pc = predictions - predictions.mean(axis=0, keepdims=True)
    Y_norm = np.sqrt((Yc * Yc).sum(axis=0))
    P_norm = np.sqrt((Pc * Pc).sum(axis=0))
    denom = Y_norm * P_norm
    denom_safe = np.where(denom > 1e-12, denom, 1.0).astype(np.float32)

    n_TRs = predictions.shape[0]
    # Explicit contiguous blocks of exactly ``block_size`` (last block may
    # be shorter). ``np.array_split`` doesn't guarantee this — with T=291
    # and block_size=10 it hands back a mix of 10- and 11-TR blocks.
    blocks = [np.arange(i, min(i + block_size, n_TRs))
              for i in range(0, n_TRs, block_size)]
    n_ge = np.zeros(true_r.shape, dtype=np.int64)

    for _ in range(n_perms):
        rng.shuffle(blocks)
        order = np.concatenate(blocks)
        num = (Yc * Pc[order]).sum(axis=0)
        r = num / denom_safe
        n_ge += (r >= true_r)

    pvalues = (n_ge + 1).astype(np.float64) / (n_perms + 1)
    return pvalues, true_r


def _pearson_r_per_col(A: np.ndarray, B: np.ndarray) -> np.ndarray:
    Ac = A - A.mean(axis=0, keepdims=True)
    Bc = B - B.mean(axis=0, keepdims=True)
    num = (Ac * Bc).sum(axis=0)
    den = np.sqrt((Ac * Ac).sum(axis=0) * (Bc * Bc).sum(axis=0))
    return num / np.where(den > 1e-12, den, 1.0)
