"""Confound regression utilities.

Regresses nuisance signals (motion, physiological noise, etc.) from
BOLD data using an fmriprep-style confounds TSV.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from denizenspipeline.preproc.errors import ConfoundsError
from denizenspipeline.preproc.manifest import ConfoundsConfig

logger = logging.getLogger(__name__)


def regress_confounds(
    bold_data: np.ndarray,
    confounds_tsv: Path | str,
    config: ConfoundsConfig,
) -> np.ndarray:
    """Regress confounds from BOLD data.

    Parameters
    ----------
    bold_data : ndarray, shape (n_trs, n_voxels)
        BOLD timeseries to clean.
    confounds_tsv : path
        Path to fmriprep-style confounds TSV.
    config : ConfoundsConfig
        Strategy, column selection, and filter settings.

    Returns
    -------
    cleaned : ndarray, shape (n_trs, n_voxels)
        With confounds regressed out.  If scrubbing is enabled, the returned
        array may have fewer TRs.
    """
    confounds_tsv = Path(confounds_tsv)
    if not confounds_tsv.exists():
        raise ConfoundsError(
            f"Confounds file not found: {confounds_tsv}",
            backend="confounds",
            subject="",
        )

    confound_matrix = _load_confounds(confounds_tsv, config)

    if confound_matrix.shape[0] != bold_data.shape[0]:
        raise ConfoundsError(
            f"Confounds TSV has {confound_matrix.shape[0]} rows but BOLD data "
            f"has {bold_data.shape[0]} TRs.",
            backend="confounds",
            subject="",
        )

    # Optional: scrub high-motion TRs
    if config.fd_threshold is not None:
        fd = _load_fd(confounds_tsv)
        if fd is not None:
            scrub_mask = fd > config.fd_threshold
            n_scrubbed = int(scrub_mask.sum())
            if n_scrubbed > 0:
                logger.info(
                    "Scrubbing %d/%d TRs (FD > %.2f mm)",
                    n_scrubbed, len(fd), config.fd_threshold,
                )
                bold_data = bold_data[~scrub_mask]
                confound_matrix = confound_matrix[~scrub_mask]

    # Optional: bandpass filter
    if config.high_pass or config.low_pass:
        bold_data = _bandpass(bold_data, config.high_pass, config.low_pass)

    # Standardize confounds
    if config.standardize:
        std = confound_matrix.std(axis=0)
        std[std == 0] = 1.0
        confound_matrix = (confound_matrix - confound_matrix.mean(axis=0)) / std

    # Add intercept
    intercept = np.ones((confound_matrix.shape[0], 1))
    design = np.hstack([confound_matrix, intercept])

    # Regress
    betas, _, _, _ = np.linalg.lstsq(design, bold_data, rcond=None)
    cleaned = bold_data - design @ betas

    # Re-add mean (we only want to remove confound variance, not the mean)
    cleaned += bold_data.mean(axis=0)

    logger.info(
        "Confound regression: %d regressors, %d TRs",
        confound_matrix.shape[1], cleaned.shape[0],
    )
    return cleaned


def _load_confounds(
    tsv_path: Path,
    config: ConfoundsConfig,
) -> np.ndarray:
    """Load confound columns based on strategy."""
    try:
        import pandas as pd
    except ImportError:
        raise ConfoundsError(
            "pandas is required for confound regression. "
            "Install with: pip install pandas",
            backend="confounds",
            subject="",
        )

    df = pd.read_csv(tsv_path, sep="\t")

    if config.strategy == "motion_24":
        cols = _motion_24_columns(df)
    elif config.strategy == "motion_6":
        cols = _motion_6_columns(df)
    elif config.strategy == "acompcor":
        acomp = [c for c in df.columns if c.startswith("a_comp_cor_")][:5]
        cols = _motion_6_columns(df) + acomp
    elif config.strategy == "custom":
        if not config.columns:
            raise ConfoundsError(
                "strategy='custom' requires columns list.",
                backend="confounds",
                subject="",
            )
        missing = [c for c in config.columns if c not in df.columns]
        if missing:
            raise ConfoundsError(
                f"Confound columns not found in TSV: {missing}",
                backend="confounds",
                subject="",
            )
        cols = list(config.columns)
    else:
        raise ConfoundsError(
            f"Unknown confound strategy: {config.strategy}. "
            f"Options: motion_24, motion_6, acompcor, custom",
            backend="confounds",
            subject="",
        )

    # Add cosine regressors if present
    cosine_cols = [c for c in df.columns if c.startswith("cosine")]
    cols += cosine_cols

    if not cols:
        raise ConfoundsError(
            f"No confound columns found for strategy '{config.strategy}'.",
            backend="confounds",
            subject="",
        )

    logger.info("Confound columns (%d): %s", len(cols), cols[:10])
    return df[cols].fillna(0).values


def _motion_6_columns(df) -> list[str]:
    """Standard 6 motion parameters (translation + rotation)."""
    candidates = ["trans_x", "trans_y", "trans_z", "rot_x", "rot_y", "rot_z"]
    return [c for c in candidates if c in df.columns]


def _motion_24_columns(df) -> list[str]:
    """24-parameter motion model: 6 params + derivatives + squared + squared derivatives."""
    base = _motion_6_columns(df)
    cols = list(base)
    for suffix in ("_derivative1", "_power2", "_derivative1_power2"):
        cols += [c + suffix for c in base if (c + suffix) in df.columns]
    return cols


def _load_fd(tsv_path: Path) -> np.ndarray | None:
    """Load framewise displacement from a confounds TSV."""
    try:
        import pandas as pd
    except ImportError:
        return None

    df = pd.read_csv(tsv_path, sep="\t")
    if "framewise_displacement" in df.columns:
        return df["framewise_displacement"].fillna(0).values
    return None


def _bandpass(
    data: np.ndarray,
    high_pass: float | None,
    low_pass: float | None,
    tr: float = 2.0,
) -> np.ndarray:
    """Apply a simple bandpass filter using scipy."""
    try:
        from scipy.signal import butter, filtfilt
    except ImportError:
        logger.warning("scipy not available — skipping bandpass filter.")
        return data

    fs = 1.0 / tr
    nyq = fs / 2.0

    if high_pass and low_pass:
        btype = "bandpass"
        Wn = [high_pass / nyq, low_pass / nyq]
    elif high_pass:
        btype = "highpass"
        Wn = high_pass / nyq
    elif low_pass:
        btype = "lowpass"
        Wn = low_pass / nyq
    else:
        return data

    b, a = butter(5, Wn, btype=btype)
    return filtfilt(b, a, data, axis=0).astype(data.dtype)
