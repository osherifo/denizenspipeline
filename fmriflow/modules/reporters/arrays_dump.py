"""ArraysDumpReporter — save per-subject result arrays as separate .npy files.

The existing ``weights`` reporter packs weights + scores + alphas into a
single HDF5. This reporter writes each array to its own ``.npy`` so they
can be loaded independently in notebooks without pulling in h5py and
without paying the disk cost when you only want one of them. It also
saves *both* metrics (Pearson r and R²) when ``ModelResult.metadata``
carries them (currently produced by the ``multiple_kernel_ridge`` model).

Outputs (under ``reporting.output_dir``):

  weights.npy           (n_train_samples, n_voxels)  — kernel/dual coefs
                                                       for MKR; primal weights
                                                       for ridge / banded ridge
  alphas.npy            (n_voxels,) — per-voxel selected regularisation
  scores_pearson_r.npy  (n_voxels,) — held-out Pearson r per voxel
  scores_r2.npy         (n_voxels,) — held-out R² per voxel
  scores.npy            (n_voxels,) — alias of scores_pearson_r when the
                                       model reported pearson_r as its
                                       primary metric (back-compat with
                                       result.scores)

Falls back gracefully when the model didn't store one of the metrics in
``metadata`` (e.g. older runs, non-MKR models) — only writes what's there.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from fmriflow.core.types import ModelResult
from fmriflow.modules._decorators import reporter

logger = logging.getLogger(__name__)


def _to_numpy(arr) -> np.ndarray:
    """Coerce cupy / torch / numpy → numpy on CPU (see weights.py)."""
    if hasattr(arr, "get") and callable(arr.get):
        try:
            return np.asarray(arr.get())
        except TypeError:
            pass
    if hasattr(arr, "detach") and hasattr(arr, "cpu"):
        return arr.detach().cpu().numpy()
    return np.asarray(arr)


@reporter("arrays_dump")
class ArraysDumpReporter:
    """Save weights, alphas, scores (r and r²) as separate .npy files."""

    name = "arrays_dump"
    PARAM_SCHEMA = {
        "subdir": {
            "type": "str",
            "description": (
                "Optional subdirectory under reporting.output_dir to keep "
                "the .npy files out of the top-level subject folder."
            ),
        },
    }

    def report(self, result: ModelResult, context, config: dict) -> dict[str, str]:
        opts = config.get("reporting", {}).get("arrays_dump", {})
        base = Path(config.get("reporting", {}).get("output_dir", "./results"))
        outdir = base / opts["subdir"] if opts.get("subdir") else base
        outdir.mkdir(parents=True, exist_ok=True)

        saved: dict[str, str] = {}

        # Always: weights, alphas, scores (whatever the model picked)
        for name, arr in [
            ("weights", result.weights),
            ("alphas", result.alphas),
            ("scores", result.scores),
        ]:
            p = outdir / f"{name}.npy"
            np.save(p, _to_numpy(arr))
            saved[name] = str(p)

        # Per-metric scores when the model put them in metadata
        meta = result.metadata or {}
        for key, fname in [
            ("scores_pearson_r", "scores_pearson_r.npy"),
            ("scores_r2", "scores_r2.npy"),
        ]:
            if key in meta:
                p = outdir / fname
                np.save(p, _to_numpy(meta[key]))
                saved[key] = str(p)

        return saved

    def validate_config(self, config: dict) -> list[str]:
        return []
