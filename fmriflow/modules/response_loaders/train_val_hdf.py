"""Response loader for per-subject HDF5 files split into a training and a validation file.

Layout (``file_pattern`` placeholders: ``{subject}``, ``{modality}``, ``{split}``)::

    {path}/{subject}_{modality}_fmri_data_trn.hdf
    {path}/{subject}_{modality}_fmri_data_val.hdf

Each file holds one dataset per story, shaped ``(n_trs, n_voxels)``, or
``(n_repeats, n_trs, n_voxels)`` for a story presented more than once (typically the
validation story). The data are already restricted to cortical voxels, so no mask
is applied and the arrays go straight to preparation.

Runs are named after the story keys (``story_01``, ...) or renamed with
``run_map``. ``ResponseData.metadata`` records the file each run came from
(``splits``), the repeats per run (``n_repeats``) and, when found, the subject's
mapper file for flatmaps (``mappers_file``; by default
``{path}/../mappers/{subject}_mappers.hdf``).

When the stimulus features stop before a silence at the end of each story, drop
those time points here with ``drop_last_trs`` so responses and features line up.

YAML config example::

    response:
      loader: train_val_hdf
      path: /data/my_study/responses
      subject: sub01
      modality: listening
      drop_last_trs: 5
    split:
      test_runs: [story_11]
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np

from fmriflow.core.types import ResponseData
from fmriflow.modules._decorators import response_loader

logger = logging.getLogger(__name__)

# Placeholder mask: the files are already cortical voxels.
_NO_MASK = np.array([True])

DEFAULT_PATTERN = "{subject}_{modality}_fmri_data_{split}.hdf"
REPEAT_MODES = ("mean", "first", "separate")


@response_loader("train_val_hdf")
class TrainValHdfResponseLoader:
    """Loads per-story responses from a subject's training and validation HDF5 files."""

    name = "train_val_hdf"

    PARAM_SCHEMA = {
        "path": {"type": "path", "required": True, "description": "Directory with the response HDF5 files"},
        "subject": {"type": "string",
                    "description": "Subject as written in file names, e.g. sub01 (default: the config's subject)"},
        "modality": {"type": "string", "required": True,
                     "description": "Modality as written in file names, e.g. listening or reading"},
        "file_pattern": {"type": "string", "default": DEFAULT_PATTERN,
                         "description": "File name with {subject}, {modality} and {split}"},
        "splits": {"type": "list[string]", "default": ["trn", "val"], "description": "Files to read, in order"},
        "stories": {"type": "list[string]", "description": "Stories to load (default: every story in the files)"},
        "repeats": {"type": "string", "default": "mean", "enum": list(REPEAT_MODES),
                    "description": "Repeated stories: average them, keep the first, or one run per repeat (<story>_rep<N>)"},
        "drop_last_trs": {"type": "int", "default": 0,
                          "description": "Time points dropped from the end of every run"},
        "run_map": {"type": "dict", "description": "Rename runs: {story: run name}"},
        "mappers_path": {"type": "path",
                         "description": "Mapper file for flatmaps (default: <path>/../mappers/<subject>_mappers.hdf if present)"},
    }

    def load(self, config: dict) -> ResponseData:
        import h5py

        resp_cfg = config.get("response", {})
        sub_cfg = config.get("subject_config", {})
        path = Path(resp_cfg["path"])
        subject = self._subject(config)
        modality = resp_cfg["modality"]
        pattern = resp_cfg.get("file_pattern", DEFAULT_PATTERN)
        wanted = set(resp_cfg["stories"]) if resp_cfg.get("stories") else None
        repeats = resp_cfg.get("repeats", "mean")
        drop = int(resp_cfg.get("drop_last_trs", 0) or 0)
        run_map = resp_cfg.get("run_map") or {}

        responses: dict[str, np.ndarray] = {}
        splits: dict[str, str] = {}
        n_repeats: dict[str, int] = {}
        seen: set[str] = set()
        for split in resp_cfg.get("splits", ["trn", "val"]):
            fpath = path / pattern.format(subject=subject, modality=modality, split=split)
            if not fpath.is_file():
                raise FileNotFoundError(f"train_val_hdf: response file not found: {fpath}")
            with h5py.File(fpath, "r") as h:
                for story in sorted(h.keys()):
                    if (wanted is not None and story not in wanted) or not isinstance(h[story], h5py.Dataset):
                        continue
                    seen.add(story)
                    arr = h[story][()]
                    for run, data in self._runs(story, arr, repeats):
                        name = run_map.get(run, run)
                        if name in responses:
                            raise ValueError(f"train_val_hdf: run {name!r} appears in both {splits[name]} and {split}")
                        responses[name] = self._clean(name, data, drop)
                        splits[name] = split
                        n_repeats[name] = int(arr.shape[0]) if arr.ndim == 3 else 1
                        logger.info("  %-24s split=%s shape=%s", name, split, responses[name].shape)
        if wanted is not None and wanted - seen:
            raise ValueError(f"train_val_hdf: stories not found in {path}: {', '.join(sorted(wanted - seen))}")

        metadata: dict[str, Any] = {"splits": splits, "n_repeats": n_repeats, "subject": subject, "modality": modality}
        mappers = self._mappers_file(resp_cfg, path, subject)
        if mappers is not None:
            metadata["mappers_file"] = str(mappers)
        logger.info("Loaded %d run(s) for %s (%s) from %s", len(responses), subject, modality, path)
        return ResponseData(
            responses=responses,
            mask=_NO_MASK,
            surface=sub_cfg.get("surface", "unknown"),
            transform=sub_cfg.get("transform", "unknown"),
            metadata=metadata,
        )

    def validate_config(self, config: dict) -> list[str]:
        resp_cfg = config.get("response", {})
        errors: list[str] = []
        path, modality, subject = resp_cfg.get("path"), resp_cfg.get("modality"), self._subject(config)
        if not path:
            errors.append("train_val_hdf loader requires response.path")
        if not modality:
            errors.append("train_val_hdf loader requires response.modality (e.g. listening)")
        if not subject:
            errors.append("train_val_hdf loader needs response.subject or the config's subject")
        if resp_cfg.get("repeats", "mean") not in REPEAT_MODES:
            errors.append(f"train_val_hdf: repeats must be one of {', '.join(REPEAT_MODES)}")
        try:
            if int(resp_cfg.get("drop_last_trs", 0) or 0) < 0:
                errors.append("train_val_hdf: drop_last_trs must be 0 or more")
        except (TypeError, ValueError):
            errors.append("train_val_hdf: drop_last_trs must be an integer")
        if errors:
            return errors
        if not Path(path).is_dir():
            return [f"train_val_hdf: response.path not found: {path}"]
        pattern = resp_cfg.get("file_pattern", DEFAULT_PATTERN)
        for split in resp_cfg.get("splits", ["trn", "val"]):
            try:
                name = pattern.format(subject=subject, modality=modality, split=split)
            except (KeyError, IndexError) as exc:
                return [f"train_val_hdf: file_pattern {pattern!r} has an unknown placeholder: {exc}"]
            if not (Path(path) / name).is_file():
                errors.append(f"train_val_hdf: response file not found: {Path(path) / name}")
        return errors

    # ── helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _subject(config: dict) -> str:
        return str(config.get("response", {}).get("subject") or config.get("subject") or "")

    @staticmethod
    def _runs(story: str, arr: np.ndarray, repeats: str) -> list[tuple[str, np.ndarray]]:
        if arr.ndim == 2:
            return [(story, arr)]
        if arr.ndim != 3:
            raise ValueError(f"train_val_hdf: {story} has shape {arr.shape}; "
                             "expected (time, voxels) or (repeats, time, voxels)")
        if repeats == "first":
            return [(story, arr[0])]
        if repeats == "separate":
            return [(f"{story}_rep{i + 1}", arr[i]) for i in range(arr.shape[0])]
        return [(story, arr.mean(axis=0))]

    @staticmethod
    def _clean(run: str, data: np.ndarray, drop: int) -> np.ndarray:
        if drop:
            if drop >= data.shape[0]:
                raise ValueError(f"train_val_hdf: drop_last_trs={drop} leaves nothing of {run} ({data.shape[0]} TRs)")
            data = data[:-drop]
        data = np.asarray(data, dtype=np.float32)
        n_nan = int(np.isnan(data).sum())
        if n_nan:
            logger.warning("train_val_hdf: %s: %d NaN value(s) replaced with 0", run, n_nan)
            data = np.nan_to_num(data, copy=False, nan=0.0)
        return data

    @staticmethod
    def _mappers_file(resp_cfg: dict, path: Path, subject: str) -> Path | None:
        if resp_cfg.get("mappers_path"):
            return Path(resp_cfg["mappers_path"])
        guess = path.parent / "mappers" / f"{subject}_mappers.hdf"
        return guess if guess.is_file() else None
