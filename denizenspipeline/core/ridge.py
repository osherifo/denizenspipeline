"""Bootstrap ridge regression for voxelwise encoding models.

Standalone implementation based on v1's ridge.py.
"""

import logging

import numpy as np

from denizenspipeline import ui

logger = logging.getLogger(__name__)


def bootstrap_ridge(Rstim, Rresp, Pstim, Presp, alphas,
                    nboots=15, chunklen=40, nchunks=20,
                    dtype=np.single, corrmin=0.2,
                    singcutoff=1e-10, normalpha=False,
                    single_alpha=False, use_corr=True):
    """Ridge regression with bootstrapped held-out set for alpha selection.

    Parameters
    ----------
    Rstim : ndarray, shape (n_train, n_features)
        Training stimuli (z-scored).
    Rresp : ndarray, shape (n_train, n_voxels)
        Training responses (z-scored).
    Pstim : ndarray, shape (n_test, n_features)
        Test stimuli (z-scored).
    Presp : ndarray, shape (n_test, n_voxels)
        Test responses (z-scored).
    alphas : array-like, shape (n_alphas,)
        Ridge parameters to test (should be log-spaced).
    nboots : int
        Number of bootstrap samples.
    chunklen : int
        Length of chunks for bootstrap sampling.
    nchunks : int
        Number of chunks held out per bootstrap sample.
    single_alpha : bool
        If True, use one alpha for all voxels.
    use_corr : bool
        If True, use correlation; if False, use R-squared.

    Returns
    -------
    weights : ndarray, shape (n_features, n_voxels)
    scores : ndarray, shape (n_voxels,)
    best_alphas : ndarray, shape (n_voxels,)
    bootstrap_corrs : ndarray, shape (n_alphas, n_voxels, nboots)
    valinds : list
    """
    ntr, nvox = Rresp.shape
    alphas = np.array(alphas)
    nalphas = len(alphas)

    # SVD of training stimuli for efficient ridge computation
    ui.console.print("       [dim]Computing SVD of training stimulus...[/]", highlight=False)
    U, S, Vt = np.linalg.svd(Rstim, full_matrices=False)

    # Remove near-zero singular values
    good_sv = S > singcutoff
    U = U[:, good_sv]
    S = S[good_sv]
    Vt = Vt[good_sv, :]

    # Precompute for efficiency
    UR = U.T @ Rresp.astype(dtype)        # (n_components, n_voxels)
    PVt = Pstim @ Vt.T                     # (n_test, n_components)

    # Bootstrap to find best alphas
    bootstrap_corrs = np.zeros((nalphas, nvox, nboots))
    valinds_list = []

    with ui.bootstrap_progress(nboots) as progress:
        task = progress.add_task("Bootstrap", total=nboots)
        for bi in range(nboots):
            # Select random chunks for validation
            allinds = range(ntr)
            indchunks = list(zip(*[iter(allinds)] * chunklen))
            if not indchunks:
                indchunks = [list(allinds)]
            n_available = len(indchunks)
            use_nchunks = min(nchunks, n_available)
            heldinds = list(range(n_available))
            np.random.shuffle(heldinds)
            heldinds = heldinds[:use_nchunks]

            valinds = []
            for hi in heldinds:
                valinds.extend(indchunks[hi])
            valinds = sorted(valinds)
            valinds_list.append(valinds)

            # Train/val split for this bootstrap
            traininds = sorted(set(range(ntr)) - set(valinds))
            U_train = U[traininds, :]
            Rresp_train = Rresp[traininds, :].astype(dtype)
            U_val = U[valinds, :]
            Rresp_val = Rresp[valinds, :].astype(dtype)

            # Precompute for this bootstrap
            UR_boot = U_train.T @ Rresp_train
            val_actual = Rresp_val

            for ai, alpha in enumerate(alphas):
                # Ridge solution via SVD: w = V diag(s/(s^2+alpha)) U^T y
                D = S / (S ** 2 + alpha)
                pred_val = U_val @ np.diag(D) @ UR_boot

                if use_corr:
                    bootstrap_corrs[ai, :, bi] = _columnwise_corr(pred_val, val_actual)
                else:
                    ss_res = np.sum((pred_val - val_actual) ** 2, axis=0)
                    ss_tot = np.sum((val_actual - val_actual.mean(0)) ** 2, axis=0)
                    bootstrap_corrs[ai, :, bi] = 1 - ss_res / (ss_tot + 1e-10)

            progress.update(task, advance=1)

    # Select best alpha per voxel (mean across bootstraps)
    mean_corrs = bootstrap_corrs.mean(axis=2)  # (n_alphas, n_voxels)

    if single_alpha:
        best_alpha_idx = np.argmax(mean_corrs.mean(axis=1))
        best_alphas = np.full(nvox, alphas[best_alpha_idx])
    else:
        best_alpha_idx = np.argmax(mean_corrs, axis=0)  # (n_voxels,)
        best_alphas = alphas[best_alpha_idx]

    # Fit final weights using best alphas on full training data
    ui.console.print("       [dim]Fitting final model with selected alphas...[/]", highlight=False)
    if single_alpha:
        D = S / (S ** 2 + best_alphas[0])
        weights = Vt.T @ np.diag(D) @ UR
    else:
        # Per-voxel alpha: compute separately for each unique alpha
        weights = np.zeros((Rstim.shape[1], nvox), dtype=dtype)
        unique_alphas = np.unique(best_alphas)
        for alpha in unique_alphas:
            vox_mask = best_alphas == alpha
            D = S / (S ** 2 + alpha)
            weights[:, vox_mask] = (Vt.T @ np.diag(D) @ UR[:, vox_mask])

    # Evaluate on test set
    pred_test = Pstim @ weights
    if use_corr:
        scores = _columnwise_corr(pred_test, Presp)
    else:
        ss_res = np.sum((pred_test - Presp) ** 2, axis=0)
        ss_tot = np.sum((Presp - Presp.mean(0)) ** 2, axis=0)
        scores = 1 - ss_res / (ss_tot + 1e-10)

    return weights, scores, best_alphas, bootstrap_corrs, valinds_list


def _columnwise_corr(a, b):
    """Compute correlation between columns of a and b.

    Parameters
    ----------
    a, b : ndarray, shape (n_samples, n_features)

    Returns
    -------
    corrs : ndarray, shape (n_features,)
    """
    a = a - a.mean(0)
    b = b - b.mean(0)
    num = (a * b).sum(0)
    denom = np.sqrt((a ** 2).sum(0) * (b ** 2).sum(0)) + 1e-10
    return num / denom
