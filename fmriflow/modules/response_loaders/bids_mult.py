"""BidsMultResponseLoader — BIDS (derivative) runs with one task per stimulus.

Built for datasets where every stimulus (e.g. a story) is its own BIDS task, some
tasks are repeated across runs, and a preprocessing tool writes several images per
run (per-echo images, weight maps) next to the one to analyse.

File selection, per ``sub-<subject>/[ses-<label>/]func/``::

    sub-<subject>[_ses-<label>]_task-<task>[_run-<n>][_echo-<n>][_desc-<desc>]_<suffix><extension>

A file is used when its suffix and ``desc`` match and it has no ``echo`` entity
(unless ``echo`` is set). Each task becomes one run named after the task;
runs of the same task are averaged (``repeats: mean``), reduced to the first, or
kept separately as ``<task>_ses-<label>_run-<n>``.

4-D NIfTI data are reordered from nibabel's ``(x, y, z, t)`` to ``(t, z, y, x)``
and masked with the pycortex mask of ``subject_config.surface`` /
``subject_config.transform``, so the transform's reference must have the data's grid.

YAML config example::

    subject: sub01
    subject_config:
      surface: sub01fs
      transform: sub01_session02
    response:
      loader: bids_mult
      path: /data/bids/derivatives/preproc
      sessions: ["02"]
      tasks: [story01, story02, story03]
      desc: preproc
      repeats: mean
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from fmriflow.core.types import ResponseData
from fmriflow.modules._decorators import response_loader

logger = logging.getLogger(__name__)

REPEAT_MODES = ("mean", "first", "separate")


def _parse_name(stem: str) -> tuple[dict[str, str], str]:
    """Split a BIDS file stem into its entities and suffix."""
    entities: dict[str, str] = {}
    suffix = ""
    for part in stem.split("_"):
        if "-" in part:
            key, _, value = part.partition("-")
            entities[key] = value
        else:
            suffix = part
    return entities, suffix


def _load_mask(surface: str, transform: str, mask_type: str) -> np.ndarray:
    import cortex
    return cortex.db.get_mask(surface, transform, mask_type)


@response_loader("bids_mult")
class BidsMultResponseLoader:
    """Loads one run per BIDS task, averaging repeated tasks, from preprocessed BIDS data."""

    name = "bids_mult"

    PARAM_SCHEMA = {
        "path": {"type": "path", "required": True, "description": "BIDS (derivatives) root directory"},
        "subject": {"type": "string", "description": "Subject label without 'sub-' (default: the config's subject)"},
        "sessions": {"type": "list[string]", "description": "Session labels (default: every ses-* folder)"},
        "tasks": {"type": "list[string]", "description": "Tasks to load, one run each (default: every task found)"},
        "desc": {"type": "string", "default": "preproc", "description": "Required desc entity; empty for files without one"},
        "suffix": {"type": "string", "default": "bold", "description": "BIDS file suffix"},
        "extension": {"type": "string", "default": ".nii.gz", "description": "File extension"},
        "echo": {"type": "int", "description": "Load this echo instead of files without an echo entity"},
        "repeats": {"type": "string", "default": "mean", "enum": list(REPEAT_MODES),
                    "description": "Several runs of one task: average them, keep the first, or keep each"},
        "run_map": {"type": "dict", "description": "Rename runs: {task: run name}"},
        "mask_type": {"type": "string", "default": "thick", "description": "Pycortex cortical mask type"},
    }

    def load(self, config: dict) -> ResponseData:
        try:
            import nibabel as nib
        except ImportError:
            raise ImportError("nibabel is required for the bids_mult response loader. "
                              "Install it with: pip install 'fmriflow[bids]'")

        resp_cfg = config.get("response", {})
        sub_cfg = config.get("subject_config", {})
        surface = sub_cfg.get("surface", "unknown")
        transform = sub_cfg.get("transform", "unknown")
        repeats = resp_cfg.get("repeats", "mean")
        run_map = resp_cfg.get("run_map") or {}

        found = self._find_runs(resp_cfg, self._subject(config))
        mask: np.ndarray | None = None
        trs: set[float] = set()
        loaded: dict[str, list[tuple[str, np.ndarray]]] = {}
        files: dict[str, list[str]] = {}

        for task, entries in found.items():
            for label, fpath in entries:
                img = nib.load(fpath)
                data = np.asarray(img.dataobj, dtype=np.float32)
                zooms = img.header.get_zooms()
                if len(zooms) > 3:
                    trs.add(round(float(zooms[3]), 4))
                if data.ndim == 4:
                    data = data.transpose(3, 2, 1, 0)          # (t, z, y, x)
                    if mask is None:
                        mask = self._mask(surface, transform, resp_cfg.get("mask_type", "thick"))
                    if mask.shape != data.shape[1:]:
                        raise ValueError(
                            f"bids_mult: {fpath.name} has grid {data.shape[1:]} (z, y, x) but the pycortex mask "
                            f"for {surface}/{transform} is {mask.shape}; use a transform made on this data's grid")
                    data = data[:, mask]
                elif data.ndim != 2:
                    raise ValueError(f"bids_mult: {fpath.name} has shape {data.shape}; expected 4-D or (time, voxels)")
                n_nan = int(np.isnan(data).sum())
                if n_nan:
                    logger.warning("bids_mult: %s: %d NaN value(s) replaced with 0", fpath.name, n_nan)
                    data = np.nan_to_num(data, copy=False, nan=0.0)
                loaded.setdefault(task, []).append((label, data))
                files.setdefault(task, []).append(str(fpath))
                logger.info("  %-28s %-18s shape=%s", task, label, data.shape)

        responses: dict[str, np.ndarray] = {}
        n_repeats: dict[str, int] = {}
        for task, runs in loaded.items():
            name = run_map.get(task, task)
            if repeats == "separate" and len(runs) > 1:
                for label, data in runs:
                    responses[f"{name}_{label}"] = data
                    n_repeats[f"{name}_{label}"] = 1
                continue
            if repeats == "mean" and len(runs) > 1:
                lengths = {data.shape[0] for _, data in runs}
                if len(lengths) > 1:
                    raise ValueError(f"bids_mult: runs of task {task} have different lengths {sorted(lengths)}; "
                                     "use repeats: first or separate")
                responses[name] = np.mean([data for _, data in runs], axis=0, dtype=np.float32)
            else:
                responses[name] = runs[0][1]
            n_repeats[name] = len(runs)

        metadata = {"files": files, "n_repeats": n_repeats}
        if len(trs) == 1:
            metadata["tr"] = trs.pop()
        elif trs:
            logger.warning("bids_mult: runs have different TRs: %s", sorted(trs))
            metadata["tr"] = sorted(trs)
        logger.info("Loaded %d run(s) from %d task(s)", len(responses), len(loaded))
        return ResponseData(
            responses=responses,
            mask=mask if mask is not None else np.array([True]),
            surface=surface,
            transform=transform,
            metadata=metadata,
        )

    def validate_config(self, config: dict) -> list[str]:
        resp_cfg = config.get("response", {})
        sub_cfg = config.get("subject_config", {})
        errors: list[str] = []
        if not resp_cfg.get("path"):
            errors.append("bids_mult loader requires response.path")
        if not self._subject(config):
            errors.append("bids_mult loader needs response.subject or the config's subject")
        tasks = resp_cfg.get("tasks")
        if tasks is not None and (not isinstance(tasks, list) or not all(isinstance(t, str) for t in tasks)):
            errors.append("bids_mult: response.tasks must be a list of task labels")
        if resp_cfg.get("repeats", "mean") not in REPEAT_MODES:
            errors.append(f"bids_mult: repeats must be one of {', '.join(REPEAT_MODES)}")
        if resp_cfg.get("extension", ".nii.gz").startswith(".nii") and (
                sub_cfg.get("surface", "unknown") == "unknown" or sub_cfg.get("transform", "unknown") == "unknown"):
            errors.append("bids_mult: NIfTI data are masked with pycortex; set subject_config.surface and .transform")
        if errors:
            return errors
        if not Path(resp_cfg["path"]).is_dir():
            return [f"bids_mult: response.path not found: {resp_cfg['path']}"]
        try:
            self._find_runs(resp_cfg, self._subject(config))
        except (FileNotFoundError, ValueError) as exc:
            errors.append(str(exc))
        return errors

    # ── helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _subject(config: dict) -> str:
        subject = str(config.get("response", {}).get("subject") or config.get("subject") or "")
        return subject[4:] if subject.startswith("sub-") else subject

    @staticmethod
    def _mask(surface: str, transform: str, mask_type: str) -> np.ndarray:
        try:
            return _load_mask(surface, transform, mask_type)
        except Exception as exc:
            raise RuntimeError(f"bids_mult: could not load the pycortex {mask_type} mask for "
                               f"surface={surface} transform={transform}: {exc}") from exc

    @staticmethod
    def _find_runs(resp_cfg: dict, subject: str) -> dict[str, list[tuple[str, Path]]]:
        """Matching files per task, in (session, run) order."""
        sub_dir = Path(resp_cfg["path"]) / f"sub-{subject}"
        if not sub_dir.is_dir():
            raise FileNotFoundError(f"bids_mult: subject folder not found: {sub_dir}")
        sessions = resp_cfg.get("sessions")
        if sessions:
            func_dirs = [sub_dir / (s if str(s).startswith("ses-") else f"ses-{s}") / "func" for s in sessions]
        else:
            func_dirs = sorted(sub_dir.glob("ses-*/func")) or [sub_dir / "func"]
        extension = resp_cfg.get("extension", ".nii.gz")
        suffix = resp_cfg.get("suffix", "bold")
        desc = resp_cfg.get("desc", "preproc") or None
        echo = resp_cfg.get("echo")
        tasks = resp_cfg.get("tasks")

        found: dict[str, list[tuple[str, Path]]] = {}
        for func_dir in func_dirs:
            if not func_dir.is_dir():
                raise FileNotFoundError(f"bids_mult: func folder not found: {func_dir}")
            for fpath in sorted(func_dir.glob(f"*{extension}")):
                entities, file_suffix = _parse_name(fpath.name[:-len(extension)])
                if file_suffix != suffix or entities.get("desc") != desc or "task" not in entities:
                    continue
                if (echo is None and "echo" in entities) or (echo is not None and entities.get("echo") != str(echo)):
                    continue
                if tasks and entities["task"] not in tasks:
                    continue
                label = "_".join(f"{k}-{entities[k]}" for k in ("ses", "run") if k in entities) or fpath.name
                found.setdefault(entities["task"], []).append((label, fpath))
        missing = [t for t in (tasks or []) if t not in found]
        if missing:
            raise ValueError(f"bids_mult: no {suffix} files with desc={desc} for task(s) {', '.join(missing)} "
                             f"under {sub_dir}")
        if not found:
            raise ValueError(f"bids_mult: no {suffix} files with desc={desc} under {sub_dir}")
        return {t: found[t] for t in (tasks or sorted(found))}
