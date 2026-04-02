"""Array utility functions: zscore, make_delayed, etc.

Pure numpy operations with no external dependencies.
Preserves the exact semantics from v1 utils.py and call_script_utils.py.
"""

import numpy as np

EPSILON = 1e-9


def zscore(a, mean=None, std=None, return_info=False):
    """Z-score normalize an array along axis 0.

    Parameters
    ----------
    a : ndarray, shape (n_samples, n_features)
        Data to normalize.
    mean : ndarray, optional
        Pre-computed mean. If None, computed from `a`.
    std : ndarray, optional
        Pre-computed std. If None, computed from `a`.
    return_info : bool
        If True, return (zscored, mean, std) tuple.

    Returns
    -------
    zscored : ndarray, same shape as `a`
    mean, std : ndarray (only if return_info=True)
    """
    if not isinstance(mean, np.ndarray):
        mean = np.nanmean(a, axis=0)
    if not isinstance(std, np.ndarray):
        std = np.nanstd(a, axis=0)

    zscored = (a - np.expand_dims(mean, axis=0)) / (np.expand_dims(std, axis=0) + EPSILON)

    if return_info:
        return zscored, mean, std
    return zscored


def mean_center(a, mean=None):
    """Mean-center an array along axis 0.

    Parameters
    ----------
    a : ndarray, shape (n_samples, n_features)
    mean : ndarray, optional

    Returns
    -------
    centered : ndarray
    mean : ndarray
    """
    if not isinstance(mean, np.ndarray):
        mean = np.mean(a, axis=0)
    return (a - np.expand_dims(mean, axis=0)), mean


def make_delayed(stim, delays, circpad=False):
    """Create concatenated delayed versions of a stimulus matrix.

    Parameters
    ----------
    stim : ndarray, shape (n_trs, n_dims)
        Stimulus features.
    delays : list of int
        Delay values in samples (can be negative, zero, or positive).
    circpad : bool
        If True, use circular padding instead of zero padding.

    Returns
    -------
    delayed : ndarray, shape (n_trs, n_dims * len(delays))
        Concatenated delayed stimulus matrices.
    """
    nt, ndim = stim.shape
    dstims = []
    for d in delays:
        dstim = np.zeros((nt, ndim), dtype=stim.dtype)
        if d < 0:
            dstim[:d, :] = stim[-d:, :]
            if circpad:
                dstim[d:, :] = stim[:-d, :]
        elif d > 0:
            dstim[d:, :] = stim[:-d, :]
            if circpad:
                dstim[:d, :] = stim[-d:, :]
        else:
            dstim = stim.copy()
        dstims.append(dstim)
    return np.hstack(dstims)


def undelay_weights(signal, delays):
    """Reshape delayed weights back to (n_delays, n_features, n_voxels).

    Parameters
    ----------
    signal : ndarray, shape (n_delayed_dims, n_voxels)
        Regression weights from a delayed model.
    delays : list of int
        The delays used when creating the delayed stimulus.

    Returns
    -------
    undelayed : ndarray, shape (n_delays, n_features, n_voxels)
    """
    if signal.ndim == 1:
        signal = signal[..., None]
    num_delayed_dims, num_voxels = signal.shape
    num_signal_dims = num_delayed_dims // len(delays)
    undelayed = np.ones((len(delays), num_signal_dims, num_voxels), dtype=signal.dtype)

    for delay_index in range(len(delays)):
        begin = delay_index * num_signal_dims
        end = (delay_index + 1) * num_signal_dims
        undelayed[delay_index, :, :] = signal[begin:end]
    return undelayed
