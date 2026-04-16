"""Reader for bling-style HDF response files.

File layout (per subject directory):
    {resp_dir}/{story}Audio_{lang}.hf5

Exception: COL english files use ``{story}.hf5`` (no "Audio_en" suffix).

Each HDF file contains a single dataset ``'s'`` with shape
``(n_reps, n_trs, n_voxels)``.  Single-repetition stories have shape
``(1, n_trs, n_voxels)``.  Repetitions are collapsed via *multirep*
(default: mean).

YAML config example:
    response:
      loader: local
      reader: bling_hdf
      path: /data/bling_reading/preprocessed/YYYYMMDDZEK
      language: en
      subject: ZEK
      multirep: mean

Required config keys:  language (en | zh)
Optional config keys:  subject  (needed for COL english exception),
                       multirep (default: mean),
                       hdf_key  (default: 's')
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from fmriflow.modules._decorators import response_reader

logger = logging.getLogger(__name__)


@response_reader("bling_hdf")
class BlingHdfReader:
    """Reads bling-style one-file-per-story HDF response data."""

    name = "bling_hdf"

    PARAM_SCHEMA = {
        "language": {"type": "string", "required": True, "enum": ["en", "zh"], "description": "Stimulus language"},
        "subject": {"type": "string", "description": "Subject identifier"},
        "multirep": {"type": "string", "default": "mean", "enum": ["mean", "first"], "description": "How to collapse repetitions"},
        "hdf_key": {"type": "string", "default": "s", "description": "HDF dataset key"},
    }

    def read(
        self, resp_dir: Path, run_names: list[str] | None, config: dict,
    ) -> dict[str, np.ndarray]:
        import h5py

        language = config["language"]
        subject = config.get("subject", "")
        multirep = config.get("multirep", "mean")
        hdf_key = config.get("hdf_key", "s")

        responses: dict[str, np.ndarray] = {}

        # Discover stories from files on disk if run_names not given
        if run_names is None:
            run_names = self._discover_stories(resp_dir, language, subject)

        for story in run_names:
            fname = self._filename(story, language, subject)
            fpath = resp_dir / fname
            if not fpath.exists():
                logger.warning("Response file not found: %s", fpath)
                continue

            with h5py.File(fpath, "r") as h:
                if hdf_key not in h:
                    logger.warning("Key '%s' not in %s", hdf_key, fpath)
                    continue
                arr = h[hdf_key][:]

            # Collapse repetitions for 3-D arrays (n_reps, n_trs, n_voxels)
            if arr.ndim == 3:
                if multirep == "mean":
                    arr = arr.mean(axis=0)
                elif multirep == "first":
                    arr = arr[0]
                else:
                    arr = arr.mean(axis=0)

            arr = arr.astype(np.float32)

            # Replace NaN with 0 and warn explicitly
            n_nan = int(np.isnan(arr).sum())
            if n_nan:
                from fmriflow import ui
                n_total = arr.size
                pct = 100.0 * n_nan / n_total
                msg = (f"{story}: {n_nan:,} NaN values "
                       f"({pct:.3f}% of {arr.shape}) replaced with 0")
                logger.warning("bling_hdf: %s", msg)
                ui.data_warning(msg)
                np.nan_to_num(arr, copy=False, nan=0.0)

            responses[story] = arr
            logger.info("  %-30s  file=%s  shape=%s", story, fname, arr.shape)

        logger.info("Loaded %d responses from %s (lang=%s, subject=%s)",
                    len(responses), resp_dir, language, subject)
        return responses

    def validate_config(self, config: dict) -> list[str]:
        errors = []
        if "language" not in config:
            errors.append("bling_hdf reader requires 'language' in config")
        lang = config.get("language", "")
        if lang not in ("en", "zh"):
            errors.append(
                f"bling_hdf reader: language must be 'en' or 'zh', got '{lang}'")
        return errors

    # -- helpers --------------------------------------------------------------

    @staticmethod
    def _filename(story: str, language: str, subject: str) -> str:
        """Build the HDF filename for a given story/language/subject."""
        # COL english files have no Audio_en suffix
        if subject.upper() == "COL" and language == "en":
            return f"{story}.hf5"
        return f"{story}Audio_{language}.hf5"

    @classmethod
    def _discover_stories(
        cls, resp_dir: Path, language: str, subject: str,
    ) -> list[str]:
        """Return sorted list of story names found in *resp_dir*."""
        stories = []
        for f in sorted(resp_dir.glob("*.hf5")):
            name = f.stem
            if subject.upper() == "COL" and language == "en":
                # COL english: files are just {story}.hf5
                # Exclude chinese files (Audio_zh suffix)
                if "Audio_" not in name:
                    stories.append(name)
            else:
                suffix = f"Audio_{language}"
                if name.endswith(suffix):
                    stories.append(name[: -len(suffix)])
        return stories
