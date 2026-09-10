"""Fit physio regressors per voxel and remove their contribution.

Two steps, as in the original pipeline:

* :func:`estimate_weights` — OLS weights of every regressor at every
  voxel (a ``(x, y, z, n_regressors)`` image). Optionally z-scores the
  BOLD series and the regressors first.
* :func:`clean` — subtracts ``regressors @ weights`` from each voxel,
  z-scores the residual and adds the voxel mean back.

Regressors live in a TSV (one column per regressor, one row per TR,
header row of names) rather than the original pickle, so any tool can
read them. TR-count mismatches between physio and BOLD are settled by
``trim`` (drop TRs at the start / end of the regressors) or ``auto_trim``
(drop the surplus at the end).

Deliberate deviations from the source: outputs are float32, and a voxel
with zero variance (outside the head) is left at its mean instead of
becoming NaN.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import numpy as np


# ── regressor TSV ───────────────────────────────────────────────────


def write_regressors(path: str | Path, X: np.ndarray, names: list[str]) -> Path:
    path = Path(path)
    X = np.asarray(X, dtype=float)
    if X.ndim != 2 or X.shape[1] != len(names):
        raise ValueError(f"regressors {X.shape} do not match {len(names)} names")
    with open(path, "w", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(names)
        for row in X:
            w.writerow([f"{v:.8g}" for v in row])
    return path


def read_regressors(path: str | Path) -> tuple[np.ndarray, list[str]]:
    path = Path(path)
    with open(path) as f:
        reader = csv.reader(f, delimiter="\t")
        names = next(reader)
        rows = [[float(v) if v not in ("", "n/a") else np.nan for v in r] for r in reader if r]
    X = np.asarray(rows, dtype=float).reshape(len(rows), len(names))
    return X, names


# ── trimming ────────────────────────────────────────────────────────


def trim_bounds(n_bold: int, n_physio: int, *, auto_trim: bool, trim_begin: int = 0, trim_end: int = 0) -> tuple[int, int]:
    """Slice ``[begin, end)`` of the regressors to line them up with the BOLD.

    ``auto_trim`` drops the surplus regressor TRs at the end. Otherwise
    ``trim_begin`` / ``trim_end`` TRs are dropped explicitly.
    """
    if auto_trim:
        surplus = n_physio - n_bold
        if surplus < 0:
            raise ValueError(f"physio has {n_physio} TRs but the BOLD has {n_bold}; auto_trim can only drop a surplus")
        return 0, n_physio - surplus
    begin = max(int(trim_begin or 0), 0)
    end = n_physio - max(int(trim_end or 0), 0)
    if end <= begin:
        raise ValueError(f"trimming {trim_begin}+{trim_end} TRs leaves nothing of {n_physio}")
    return begin, end


def aligned_regressors(X: np.ndarray, n_bold: int, *, auto_trim: bool, trim_begin: int = 0, trim_end: int = 0,
                       zscore: bool = True) -> np.ndarray:
    b, e = trim_bounds(n_bold, X.shape[0], auto_trim=auto_trim, trim_begin=trim_begin, trim_end=trim_end)
    X = np.array(X[b:e], dtype=float)
    if X.shape[0] != n_bold:
        raise ValueError(
            f"{X.shape[0]} physio TRs != {n_bold} BOLD TRs after trimming; "
            f"set trim_begin/trim_end (or auto_trim) so they match"
        )
    if np.isnan(X).any():
        raise ValueError("the regressors contain NaNs (a block too short for the model?)")
    if zscore:
        constant = np.nonzero(X.std(axis=0) == 0)[0]
        if constant.size:
            raise ValueError(
                f"regressor column(s) {constant.tolist()} are constant after trimming, so they cannot be "
                f"z-scored; drop them from the model or trim fewer TRs"
            )
        X = _zscore(X, axis=0)
    return X


def _zscore(x: np.ndarray, axis: int = 0) -> np.ndarray:
    m = x.mean(axis=axis, keepdims=True)
    sd = x.std(axis=axis, keepdims=True)
    out = x - m
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(sd > 0, out / sd, 0.0)
    return out


# ── estimate / clean ────────────────────────────────────────────────


def _load_bold(path: str | Path):
    import nibabel as nib
    img = nib.load(str(path))
    if len(img.shape) != 4:
        raise ValueError(f"expected a 4-D BOLD image, got shape {img.shape} for {path}")
    return img


def estimate_weights(
    bold_file: str | Path, regressors_file: str | Path, out_file: str | Path, *,
    zscore_image: bool = True, zscore_physio: bool = True,
    auto_trim: bool = False, trim_begin: int = 0, trim_end: int = 0,
) -> dict[str, Any]:
    """Per-voxel OLS weights of the regressors → ``out_file`` (x, y, z, n_regressors)."""
    import nibabel as nib

    img = _load_bold(bold_file)
    n_trs = img.shape[3]
    X, names = read_regressors(regressors_file)
    X = aligned_regressors(X, n_trs, auto_trim=auto_trim, trim_begin=trim_begin, trim_end=trim_end, zscore=zscore_physio)
    pinv = np.linalg.pinv(X, rcond=1e-08)                     # (n_reg, n_trs)

    data = np.asarray(img.dataobj, dtype=np.float32)
    x, y, z, _ = data.shape
    weights = np.zeros((x, y, z, X.shape[1]), dtype=np.float32)
    for k in range(z):                                         # one slice at a time keeps memory bounded
        Y = data[:, :, k, :].reshape(-1, n_trs).T.astype(np.float64)   # (n_trs, n_vox)
        if zscore_image:
            Y = _zscore(Y, axis=0)
        weights[:, :, k, :] = (pinv @ Y).T.reshape(x, y, X.shape[1])

    out = nib.Nifti1Image(weights, img.affine, img.header)
    out.set_data_dtype(np.float32)
    out.header["descrip"] = b"physio weights"
    out.to_filename(str(out_file))
    return {"n_trs": int(n_trs), "n_regressors": int(X.shape[1]), "regressor_names": names,
            "n_nan_inf": int(np.sum(~np.isfinite(weights)))}


def clean(
    bold_file: str | Path, regressors_file: str | Path, weights_file: str | Path, out_file: str | Path, *,
    zscore_image: bool = True, zscore_physio: bool = True,
    auto_trim: bool = False, trim_begin: int = 0, trim_end: int = 0,
    variance_map_file: str | Path | None = None,
) -> dict[str, Any]:
    """Remove the fitted physio contribution from each voxel → ``out_file``.

    Per slice: the voxel mean is kept, the series is z-scored when the
    weights were estimated on z-scored data, ``regressors @ weights`` is
    subtracted, and the residual is z-scored and offset by the mean.
    Returns a summary with the fraction of variance removed (overall and per-voxel
    percentiles); ``variance_map_file`` receives the per-voxel fraction as a 3-D image.
    """
    import nibabel as nib

    img = _load_bold(bold_file)
    n_trs = img.shape[3]
    X, _ = read_regressors(regressors_file)
    X = aligned_regressors(X, n_trs, auto_trim=auto_trim, trim_begin=trim_begin, trim_end=trim_end, zscore=zscore_physio)
    w_img = nib.load(str(weights_file))
    weights = np.asarray(w_img.dataobj, dtype=np.float32)
    if weights.shape[:3] != img.shape[:3] or weights.shape[3] != X.shape[1]:
        raise ValueError(f"weights {weights.shape} do not match BOLD {img.shape[:3]} × {X.shape[1]} regressors")

    data = np.asarray(img.dataobj, dtype=np.float32)
    x, y, z, _ = data.shape
    out_data = np.empty_like(data)
    removed_map = np.zeros((x, y, z), dtype=np.float32)      # per-voxel fraction of variance removed
    live_map = np.zeros((x, y, z), dtype=bool)                # which voxels are real signal (sd > 0), not background
    var_before = 0.0
    var_after = 0.0
    for k in range(z):
        Y = data[:, :, k, :].reshape(-1, n_trs).T.astype(np.float64)   # (n_trs, n_vox)
        W = weights[:, :, k, :].reshape(-1, X.shape[1]).T.astype(np.float64)  # (n_reg, n_vox)
        mean = Y.mean(axis=0)
        sd = Y.std(axis=0)
        live = sd > 0
        if zscore_image:
            Y = _zscore(Y, axis=0)
        fitted = X @ W
        residual = Y - fitted
        vb = Y.var(axis=0)
        va = residual.var(axis=0)
        var_before += float(np.sum(vb[live]))
        var_after += float(np.sum(va[live]))
        with np.errstate(divide="ignore", invalid="ignore"):
            frac = np.where(live & (vb > 0), 1.0 - va / vb, 0.0)
        removed_map[:, :, k] = frac.reshape(x, y).astype(np.float32)
        live_map[:, :, k] = live.reshape(x, y)
        cleaned = _zscore(residual, axis=0) + mean
        cleaned[:, ~live] = mean[~live]
        out_data[:, :, k, :] = cleaned.T.reshape(x, y, n_trs).astype(np.float32)

    out = nib.Nifti1Image(out_data, img.affine, img.header)
    out.set_data_dtype(np.float32)
    out.to_filename(str(out_file))
    if variance_map_file is not None:
        vm = nib.Nifti1Image(removed_map, img.affine)
        vm.set_data_dtype(np.float32)
        vm.to_filename(str(variance_map_file))
    removed = 1.0 - var_after / var_before if var_before > 0 else 0.0
    # Every live voxel, including one the correction did nothing for or made
    # worse (frac <= 0) — `removed_map > 0` would silently drop those and
    # bias the percentiles toward looking better than the fit actually is.
    live_frac = removed_map[live_map]
    return {"n_trs": int(n_trs), "n_regressors": int(X.shape[1]),
            "variance_removed_fraction": round(float(removed), 6),
            "variance_removed_p50": round(float(np.median(live_frac)), 6) if live_frac.size else 0.0,
            "variance_removed_p95": round(float(np.percentile(live_frac, 95)), 6) if live_frac.size else 0.0,
            "n_nan_inf": int(np.sum(~np.isfinite(out_data)))}
