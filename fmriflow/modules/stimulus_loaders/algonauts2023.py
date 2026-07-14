"""Algonauts2023StimulusLoader — training images for the Algonauts 2023 challenge.

Emits one :class:`ImageSeqStim` (the ``"train"`` pseudo-run) pointing at the
subject's training-image directory.  Images are *not* decoded here — the
``alexnet`` (or ``clip``) feature extractor reads them on demand.

Image order is the **sorted filename order**, which matches the row order of the
fMRI arrays read by :mod:`fmriflow.modules.response_loaders.algonauts2023`
(Algonauts names images ``train-0001_nsd-XXXXX.png`` … so they sort into
presentation order).  Feature row *i* therefore aligns with response row *i*.

Expected on-disk layout (the challenge dev-kit tree under ``data_dir``)::

    {data_dir}/{subject}/training_split/training_images/*.png
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from fmriflow.core.types import ImageSeqStim, StimRun, StimulusData
from fmriflow.modules._decorators import stimulus_loader

logger = logging.getLogger(__name__)


@stimulus_loader("algonauts2023")
class Algonauts2023StimulusLoader:
    """Emit one ImageSeqStim over the subject's training images."""

    name = "algonauts2023"

    PARAM_SCHEMA = {
        "data_dir": {"type": "path", "required": True, "description": "Root of the Algonauts 2023 dev-kit tree"},
        "subject": {"type": "string", "description": "Subject id, e.g. subj01 (defaults to config.subject)"},
    }

    def load(self, config: dict) -> StimulusData:
        stim_cfg = config.get("stimulus", {})
        data_dir = Path(stim_cfg["data_dir"])
        subject = stim_cfg.get("subject") or config.get("subject")

        img_dir = data_dir / subject / "training_split" / "training_images"
        files = sorted(img_dir.glob("*.png")) or sorted(img_dir.glob("*.jpg"))
        if not files:
            raise FileNotFoundError(f"no training images under {img_dir}")

        run = "train"
        runs = {
            run: StimRun(
                name=run,
                stimulus=ImageSeqStim(
                    source=str(img_dir),
                    image_ids=np.arange(len(files)),   # sorted-file order
                    source_kind="image_dir",
                ),
                modality="visual",
            )
        }
        logger.info("algonauts2023 %s: %d training images", subject, len(files))
        return StimulusData(runs=runs, metadata={"dataset": "algonauts2023", "subject": subject})

    def validate_config(self, config: dict) -> list[str]:
        errors = []
        stim_cfg = config.get("stimulus", {})
        if "data_dir" not in stim_cfg:
            errors.append("algonauts2023 stimulus loader requires stimulus.data_dir")
        elif not Path(stim_cfg["data_dir"]).is_dir():
            errors.append(f"stimulus.data_dir not found: {stim_cfg['data_dir']}")
        return errors
