"""Reader for narratives-style HDF response files.

File layout (per subject directory):
    {resp_dir}/{story}Audio_{lang}.hf5

Exception: some collections use ``{story}.hf5`` (no ``Audio_{lang}``
suffix) for one language; toggle with ``no_language_suffix``.

Each HDF file contains a single dataset ``'s'`` with shape
``(n_reps, n_trs, n_voxels)``.  Single-repetition stories have shape
``(1, n_trs, n_voxels)``.  Repetitions are collapsed via *multirep*
(default: mean).

YAML config example:
    response:
      loader: local
      reader: narratives_hdf
      path: /data/narratives/preprocessed/sub01
      language: en
      subject: sub01
      multirep: mean

Required config keys:  language (en | zh)
Optional config keys:  subject                (used for file discovery),
                       no_language_suffix     (bool; drops "Audio_{lang}"),
                       multirep               (default: mean),
                       hdf_key                (default: 's')
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from fmriflow.modules._decorators import response_reader

logger = logging.getLogger(__name__)


@response_reader("narratives_hdf")
class NarrativesHdfReader:
    """Reads narratives-style one-file-per-story HDF response data."""

    name = "narratives_hdf"

    PARAM_SCHEMA = {
        "language": {"type": "string", "required": True, "enum": ["en", "zh"], "description": "Stimulus language"},
        "subject": {"type": "string", "description": "Subject identifier"},
        "no_language_suffix": {"type": "bool", "default": False, "description": "Use '{story}.hf5' instead of '{story}Audio_{lang}.hf5'"},
        "multirep": {"type": "string", "default": "mean", "enum": ["mean", "first"], "description": "How to collapse repetitions"},
        "hdf_key": {"type": "string", "default": "s", "description": "HDF dataset key"},
    }

    def read(
        self, resp_dir: Path, run_names: list[str] | None, config: dict,
    ) -> dict[str, np.ndarray]:
        import h5py

        language = config["language"]
        subject = config.get("subject", "")
        no_language_suffix = bool(config.get("no_language_suffix", False))
        multirep = config.get("multirep", "mean")
        hdf_key = config.get("hdf_key", "s")

        responses: dict[str, np.ndarray] = {}

        # Discover stories from files on disk if run_names not given
        if run_names is None:
            run_names = self._discover_stories(
                resp_dir, language, no_language_suffix)

        for story in run_names:
            fname = self._filename(story, language, no_language_suffix)
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
                logger.warning("narratives_hdf: %s", msg)
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
            errors.append("narratives_hdf reader requires 'language' in config")
        lang = config.get("language", "")
        if lang not in ("en", "zh"):
            errors.append(
                f"narratives_hdf reader: language must be 'en' or 'zh', got '{lang}'")
        return errors

    # -- helpers --------------------------------------------------------------

    @staticmethod
    def _filename(story: str, language: str, no_language_suffix: bool) -> str:
        """Build the HDF filename for a given story/language."""
        if no_language_suffix:
            return f"{story}.hf5"
        return f"{story}Audio_{language}.hf5"

    @classmethod
    def _discover_stories(
        cls, resp_dir: Path, language: str, no_language_suffix: bool,
    ) -> list[str]:
        """Return sorted list of story names found in *resp_dir*."""
        stories = []
        for f in sorted(resp_dir.glob("*.hf5")):
            name = f.stem
            if no_language_suffix:
                # Files are just {story}.hf5 — exclude any files that do
                # carry the ``Audio_<lang>`` suffix.
                if "Audio_" not in name:
                    stories.append(name)
            else:
                suffix = f"Audio_{language}"
                if name.endswith(suffix):
                    stories.append(name[: -len(suffix)])
        return stories
