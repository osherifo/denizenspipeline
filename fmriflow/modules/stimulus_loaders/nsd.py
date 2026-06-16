"""NsdStimulusLoader — per-trial image references for an image-viewing dataset.

Reads the behavioural ``responses.tsv`` to recover, for each scan session, the
ordered sequence of images shown (one per trial), and emits an
:class:`ImageSeqStim` per session pointing at the shared image store.  Images
are *not* decoded here — the ``clip`` feature extractor reads them on demand.

Trial order matches :mod:`fmriflow.modules.response_loaders.nsd` (sorted by
``(RUN, TRIAL)`` within a session), so feature row *t* aligns with response
row *t*.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from fmriflow.core.types import ImageSeqStim, StimRun, StimulusData
from fmriflow.modules._decorators import stimulus_loader

logger = logging.getLogger(__name__)

# Public dataset stimuli file (read remotely if no local copy is given).
_DEFAULT_IMAGES = (
    "s3://natural-scenes-dataset/nsddata_stimuli/stimuli/nsd/nsd_stimuli.hdf5"
)


@stimulus_loader("nsd")
class NsdStimulusLoader:
    """Emit one ImageSeqStim per session from the behavioural design."""

    name = "nsd"

    PARAM_SCHEMA = {
        "raw_dir": {"type": "path", "required": True, "description": "Root of the downloaded dataset tree"},
        "subject": {"type": "string", "description": "Subject id, e.g. subj01 (defaults to config.subject)"},
        "sessions": {"type": "list[int]", "required": True, "description": "Session numbers (one run each)"},
        "images": {"type": "string", "default": _DEFAULT_IMAGES, "description": "HDF5 image store (local path or s3:// URL)"},
        "dataset": {"type": "string", "default": "imgBrick", "description": "Dataset name inside the HDF5 image store"},
    }

    def load(self, config: dict) -> StimulusData:
        stim_cfg = config.get("stimulus", {})
        raw_dir = Path(stim_cfg["raw_dir"])
        subject = stim_cfg.get("subject") or config.get("subject")
        sessions = list(stim_cfg["sessions"])
        images = stim_cfg.get("images", _DEFAULT_IMAGES)
        dataset = stim_cfg.get("dataset", "imgBrick")

        behav_path = raw_dir / "nsddata" / "ppdata" / subject / "behav" / "responses.tsv"
        ses_ids = self._trial_image_ids(behav_path, sessions)

        runs: dict[str, StimRun] = {}
        for ses in sessions:
            run = f"ses{ses:02d}"
            ids_1based = ses_ids[ses]
            runs[run] = StimRun(
                name=run,
                stimulus=ImageSeqStim(
                    source=images,
                    image_ids=ids_1based - 1,   # 73KID is 1-based; store 0-based
                    source_kind="hdf5",
                    dataset=dataset,
                ),
                modality="visual",
            )
            logger.info("  %s: %d images", run, ids_1based.shape[0])

        return StimulusData(runs=runs, metadata={"dataset": "nsd", "subject": subject})

    @staticmethod
    def _trial_image_ids(behav_path: Path, sessions: list[int]) -> dict[int, np.ndarray]:
        import pandas as pd

        df = pd.read_csv(behav_path, sep="\t")
        out = {}
        for ses in sessions:
            sub = df[df["SESSION"] == ses].sort_values(["RUN", "TRIAL"])
            out[ses] = sub["73KID"].to_numpy().astype(int)
        return out

    def validate_config(self, config: dict) -> list[str]:
        errors = []
        stim_cfg = config.get("stimulus", {})
        if "raw_dir" not in stim_cfg:
            errors.append("nsd stimulus loader requires stimulus.raw_dir")
        elif not Path(stim_cfg["raw_dir"]).is_dir():
            errors.append(f"stimulus.raw_dir not found: {stim_cfg['raw_dir']}")
        if "sessions" not in stim_cfg:
            errors.append("nsd stimulus loader requires stimulus.sessions")
        return errors
