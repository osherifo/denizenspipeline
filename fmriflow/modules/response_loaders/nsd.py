"""NsdResponseLoader — single-trial betas for an image-viewing dataset.

Loads per-session GLM betas (one pseudo-run per scan session), masks them to a
cortical ROI, and scales the int16 betas to percent-signal-change.  Returns 2-D
``(n_trials, n_voxels)`` arrays so the prepare/model stages need no surface
geometry, while still carrying the **real 3-D ROI mask** plus the pycortex
``surface``/``transform`` so flatmap reporters can rebuild the full volume.

Trial order within a session follows ``responses.tsv`` sorted by ``(RUN, TRIAL)``,
which matches the betas 4th axis, so row *t* of the returned array is trial *t*.

Expected on-disk layout (mirrors the public dataset tree under ``raw_dir``)::

    {raw_dir}/nsddata_betas/ppdata/{subject}/{space}/{betas_version}/betas_session{NN}.nii.gz
    {raw_dir}/nsddata/ppdata/{subject}/{space}/roi/{roi}.nii.gz
    {raw_dir}/nsddata/ppdata/{subject}/behav/responses.tsv
    {raw_dir}/nsddata/experiments/nsd/nsd_stim_info_merged.csv   (optional; shared1000 split)
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from fmriflow.core.types import ResponseData
from fmriflow.modules._decorators import response_loader

logger = logging.getLogger(__name__)


@response_loader("nsd")
class NsdResponseLoader:
    """Load NSD-style single-trial betas as pre-masked per-session responses."""

    name = "nsd"

    PARAM_SCHEMA = {
        "raw_dir": {"type": "path", "required": True, "description": "Root of the downloaded dataset tree"},
        "subject": {"type": "string", "description": "Subject id, e.g. subj01 (defaults to config.subject)"},
        "space": {"type": "string", "default": "func1pt8mm", "description": "Functional space directory"},
        "betas_version": {"type": "string", "default": "betas_fithrf_GLMdenoise_RR", "description": "Betas GLM version directory"},
        "roi": {"type": "string", "default": "nsdgeneral", "description": "ROI mask name (under roi/), > 0 selects voxels"},
        "sessions": {"type": "list[int]", "required": True, "description": "Session numbers to load (one pseudo-run each)"},
        "scale": {"type": "float", "default": 300.0, "description": "Divisor turning int16 betas into percent signal change"},
    }

    def load(self, config: dict) -> ResponseData:
        resp_cfg = config.get("response", {})
        sub_cfg = config.get("subject_config", {})

        raw_dir = Path(resp_cfg["raw_dir"])
        subject = resp_cfg.get("subject") or config.get("subject")
        space = resp_cfg.get("space", "func1pt8mm")
        betas_version = resp_cfg.get("betas_version", "betas_fithrf_GLMdenoise_RR")
        roi = resp_cfg.get("roi", "nsdgeneral")
        sessions = list(resp_cfg["sessions"])
        scale = float(resp_cfg.get("scale", 300.0))

        # pycortex names are carried through for flatmap reporters; the loader
        # itself does not need them (it masks with the on-disk ROI).
        surface = sub_cfg.get("surface", "unknown")
        transform = sub_cfg.get("transform", "unknown")

        betas_dir = raw_dir / "nsddata_betas" / "ppdata" / subject / space / betas_version
        mask_path = raw_dir / "nsddata" / "ppdata" / subject / space / "roi" / f"{roi}.nii.gz"
        behav_path = raw_dir / "nsddata" / "ppdata" / subject / "behav" / "responses.tsv"

        mask_3d, flat_mask = self._load_mask(mask_path)
        logger.info("NSD %s mask '%s': %d voxels", subject, roi, int(flat_mask.sum()))

        ses_ids = self._trial_image_ids(behav_path, sessions)
        shared = self._shared1000_map(raw_dir, ses_ids)

        responses: dict[str, np.ndarray] = {}
        trial_image_ids: dict[str, np.ndarray] = {}
        shared_mask: dict[str, np.ndarray] = {}
        for ses in sessions:
            run = f"ses{ses:02d}"
            resp = self._load_betas_masked(betas_dir / f"betas_session{ses:02d}.nii.gz",
                                           flat_mask, scale)
            ids = ses_ids[ses]
            if resp.shape[0] != ids.shape[0]:
                raise ValueError(
                    f"{run}: betas have {resp.shape[0]} trials but responses.tsv "
                    f"lists {ids.shape[0]} — trial/beta ordering mismatch.")
            responses[run] = resp
            trial_image_ids[run] = ids
            if shared is not None:
                shared_mask[run] = shared[ses]
            logger.info("  %s: responses %s", run, resp.shape)

        metadata: dict = {
            "dataset": "nsd",
            "subject": subject,
            "space": space,
            "trial_image_ids": trial_image_ids,
        }
        if shared_mask:
            # Per-run boolean test masks consumed by the trial-level split.
            metadata["trial_split"] = {"shared1000": shared_mask}

        return ResponseData(
            responses=responses,
            mask=mask_3d,
            surface=surface,
            transform=transform,
            metadata=metadata,
        )

    # ── private helpers ─────────────────────────────────────────────────

    @staticmethod
    def _load_mask(mask_path: Path) -> tuple[np.ndarray, np.ndarray]:
        import nibabel as nib

        mask_3d = nib.load(mask_path).get_fdata() > 0
        return mask_3d, mask_3d.reshape(-1)

    @staticmethod
    def _load_betas_masked(betas_path: Path, flat_mask: np.ndarray,
                           scale: float) -> np.ndarray:
        """(n_trials, n_voxels) float32 percent-signal-change."""
        import nibabel as nib

        img = nib.load(betas_path)
        data = np.asarray(img.dataobj)              # (X, Y, Z, T) int16
        data = data.reshape(-1, data.shape[-1])     # (n_vox_all, T)
        return (data[flat_mask, :].T.astype(np.float32)) / scale

    @staticmethod
    def _trial_image_ids(behav_path: Path, sessions: list[int]) -> dict[int, np.ndarray]:
        """Per session: ordered 73KID (1-indexed) in (RUN, TRIAL) order."""
        import pandas as pd

        df = pd.read_csv(behav_path, sep="\t")
        out = {}
        for ses in sessions:
            sub = df[df["SESSION"] == ses].sort_values(["RUN", "TRIAL"])
            out[ses] = sub["73KID"].to_numpy().astype(int)
        return out

    @staticmethod
    def _shared1000_map(raw_dir: Path,
                        ses_ids: dict[int, np.ndarray]) -> dict[int, np.ndarray] | None:
        """Per session: boolean array marking shared1000 trials, or None if absent."""
        import pandas as pd

        info_path = raw_dir / "nsddata" / "experiments" / "nsd" / "nsd_stim_info_merged.csv"
        if not info_path.exists():
            logger.info("nsd_stim_info_merged.csv not found — shared1000 split unavailable")
            return None

        info = pd.read_csv(info_path, usecols=["nsdId", "shared1000"])
        # nsdId is the 0-based 73k index; 73KID is 1-based -> shared[73KID - 1].
        shared_by_nsdid = info.sort_values("nsdId")["shared1000"].to_numpy().astype(bool)
        return {ses: shared_by_nsdid[ids - 1] for ses, ids in ses_ids.items()}

    def validate_config(self, config: dict) -> list[str]:
        errors = []
        resp_cfg = config.get("response", {})
        if "raw_dir" not in resp_cfg:
            errors.append("nsd loader requires response.raw_dir")
        elif not Path(resp_cfg["raw_dir"]).is_dir():
            errors.append(f"response.raw_dir not found: {resp_cfg['raw_dir']}")
        if "sessions" not in resp_cfg:
            errors.append("nsd loader requires response.sessions")
        return errors
