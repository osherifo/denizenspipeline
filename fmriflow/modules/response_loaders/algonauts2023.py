"""Algonauts2023ResponseLoader — fsaverage-surface fMRI for the Algonauts 2023 challenge.

Loads the per-subject training fMRI (left/right hemisphere ``.npy`` arrays in
fsaverage "challenge space"), concatenates the hemispheres into one 2-D
``(n_images, n_vertices)`` matrix, and returns it as a single ``"train"``
pseudo-run.  Because the array is 2-D, the prepare/model stages need no surface
geometry; the fsaverage vertex masks are carried in ``metadata`` so a flatmap
reporter can expand scores back onto the full fsaverage surface.

Row order matches the sorted training-image order emitted by
:mod:`fmriflow.modules.stimulus_loaders.algonauts2023`, so response row *i*
aligns with feature row *i*.

A held-out validation set is carried as a per-run boolean mask under
``metadata['trial_split']['val']`` (a seeded random ``val_fraction`` of images),
so a config can hold it out with ``split.test_trials: val`` — the challenge has
no separate labelled test fMRI, so we validate on a slice of the training set.

Expected on-disk layout (the challenge dev-kit tree under ``data_dir``)::

    {data_dir}/{subject}/training_split/training_fmri/{lh,rh}_training_fmri.npy
    {data_dir}/{subject}/roi_masks/{lh,rh}.all-vertices_fsaverage_space.npy
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from fmriflow.core.types import ResponseData
from fmriflow.modules._decorators import response_loader

logger = logging.getLogger(__name__)

# Sentinel triggering the 2-D ingest path (no pycortex masking); the real
# fsaverage vertex masks ride in metadata for the flatmap reporter.
_NO_MASK = np.array([True])


@response_loader("algonauts2023")
class Algonauts2023ResponseLoader:
    """Load Algonauts 2023 fsaverage-surface fMRI as a 2-D response matrix."""

    name = "algonauts2023"

    PARAM_SCHEMA = {
        "data_dir": {"type": "path", "required": True, "description": "Root of the Algonauts 2023 dev-kit tree"},
        "subject": {"type": "string", "description": "Subject id, e.g. subj01 (defaults to config.subject)"},
        "hemispheres": {"type": "list[str]", "default": ["lh", "rh"], "description": "Hemispheres to load and concatenate"},
        "val_fraction": {"type": "float", "default": 0.1, "description": "Fraction of training images held out as validation (split.test_trials: val)"},
        "val_seed": {"type": "int", "default": 0, "description": "RNG seed for the validation split"},
    }

    def load(self, config: dict) -> ResponseData:
        resp_cfg = config.get("response", {})
        data_dir = Path(resp_cfg["data_dir"])
        subject = resp_cfg.get("subject") or config.get("subject")
        hemis = list(resp_cfg.get("hemispheres", ["lh", "rh"]))
        val_fraction = float(resp_cfg.get("val_fraction", 0.1))
        val_seed = int(resp_cfg.get("val_seed", 0))

        subj_dir = data_dir / subject
        fmri_dir = subj_dir / "training_split" / "training_fmri"
        roi_dir = subj_dir / "roi_masks"

        arrays, hemi_dims = [], {}
        for h in hemis:
            arr = np.load(fmri_dir / f"{h}_training_fmri.npy").astype(np.float32)
            arrays.append(arr)
            hemi_dims[h] = int(arr.shape[1])
            logger.info("  %s: %s vertices %d", subject, h, arr.shape[1])
        resp = np.concatenate(arrays, axis=1)   # (n_images, sum n_vertices)
        n_img = resp.shape[0]
        if any(a.shape[0] != n_img for a in arrays):
            raise ValueError("hemisphere fMRI arrays disagree on image count")

        # Seeded validation holdout, carried for split.test_trials: val.
        n_val = int(round(n_img * val_fraction))
        val_mask = np.zeros(n_img, dtype=bool)
        val_idx = np.random.default_rng(val_seed).permutation(n_img)[:n_val]
        val_mask[val_idx] = True

        # fsaverage all-vertices masks (challenge-space -> full fsaverage) for flatmaps.
        fsavg_masks = {}
        for h in hemis:
            p = roi_dir / f"{h}.all-vertices_fsaverage_space.npy"
            if p.exists():
                fsavg_masks[h] = np.load(p).astype(bool)

        run = "train"
        metadata = {
            "dataset": "algonauts2023",
            "subject": subject,
            "hemispheres": hemis,
            "hemi_dims": hemi_dims,
            "fsaverage_masks": fsavg_masks,
            "trial_split": {"val": {run: val_mask}},
        }
        logger.info("  %s: responses %s (val %d/%d)", subject, resp.shape, n_val, n_img)
        return ResponseData(
            responses={run: resp},
            mask=_NO_MASK,
            surface="fsaverage",
            transform="",
            metadata=metadata,
        )

    def validate_config(self, config: dict) -> list[str]:
        errors = []
        resp_cfg = config.get("response", {})
        if "data_dir" not in resp_cfg:
            errors.append("algonauts2023 loader requires response.data_dir")
        elif not Path(resp_cfg["data_dir"]).is_dir():
            errors.append(f"response.data_dir not found: {resp_cfg['data_dir']}")
        return errors
