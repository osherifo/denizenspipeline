"""NpzConcatSource — loads pre-trimmed features stored as one big concatenated
matrix per phase inside an .npz file.

Use case: a precomputed feature distributed as one big concatenated
``.npz`` per phase (e.g. motion energy), where the train phase is a
single ``(T_concat, D)`` array spanning every training run and the
validation phase is a ``(k_reps, T_val, D)`` array for a single
repeated validation story. The pipeline needs per-run blocks
keyed by run name, so the loader splits the concatenated arrays back
into per-run pieces using an explicit ordered length map the user
provides.

Config (single file with both phases)::

    features:
      - name: motion_energy
        source: npz_concat
        path: /data/.../motion_energy.npz
        train:
          key: moten_Rstim                       # (T_concat, D)
          runs:                                  # name → row count, IN ORDER
            story_01: 374
            story_02: 397
            ...
            story_10: 365
        val:
          key: moten_Pstim                       # (k_reps, T_val, D)  -or-  (T_val, D)
          repeat: 0                              # int index or 'mean' (default 0)
          runs:
            story_11: 291

Config (train + val in separate files)::

    features:
      - name: motion_energy
        source: npz_concat
        paths:
          train: /data/.../moten_train.npz
          val:   /data/.../moten_val.npz
        train: {key: moten_Rstim, runs: {...}}
        val:   {key: moten_Pstim, runs: {...}}

Either phase block may be omitted (e.g. for a train-only file). Only
runs listed under ``train.runs`` / ``val.runs`` are returned; the
orchestrator filters further via ``split.test_runs``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from fmriflow.core.types import FeatureSet
from fmriflow.modules._decorators import feature_source


@feature_source("npz_concat")
class NpzConcatSource:
    """Load a feature stored as a concatenated train (and val) array in one
    or two .npz files, splitting back into per-run blocks by length."""

    name = "npz_concat"
    PARAM_SCHEMA = {
        "name": {"type": "string", "required": True, "description": "Feature name"},
        "path": {"type": "path", "description": "Single .npz holding both train and val arrays"},
        "paths": {"type": "dict", "description": "Per-phase .npz paths (train/val) if split across files"},
        "train": {"type": "dict", "description": "Train phase: {key, runs: ordered-dict of npz-key→length}"},
        "val": {"type": "dict", "description": "Val phase: {key, runs, optional repeat}"},
        "run_map": {"type": "dict", "description": "Map npz row-block names → pipeline run names (same format as response.run_map)"},
    }

    def load(self, run_names: list[str], config: dict) -> FeatureSet:
        feature_name = config['name']
        wanted = set(run_names)
        run_map: dict[str, str] = config.get('run_map') or {}
        data: dict[str, np.ndarray] = {}

        for phase in ('train', 'val'):
            phase_cfg = config.get(phase)
            if not isinstance(phase_cfg, dict):
                continue
            arr = _load_phase_array(config, phase, phase_cfg)
            for src_name, block in _split_phase(arr, phase_cfg).items():
                # Translate the npz-side block name (e.g. ``story_01``) to
                # the pipeline run name (e.g. ``alternateithicatom``);
                # blocks whose translated name isn't requested by the
                # orchestrator are dropped.
                pipeline_name = run_map.get(src_name, src_name)
                if wanted and pipeline_name not in wanted:
                    continue
                data[pipeline_name] = block

        if not data:
            return FeatureSet(name=feature_name, data={}, n_dims=0)
        n_dims = next(iter(data.values())).shape[1]
        return FeatureSet(name=feature_name, data=data, n_dims=n_dims)

    def validate_config(self, config: dict) -> list[str]:
        errors: list[str] = []

        path_field = config.get('path')
        paths_field = config.get('paths')
        if path_field is None and paths_field is None:
            errors.append("npz_concat requires 'path' (single file) or 'paths' (per-phase)")
        if path_field is not None and not Path(path_field).is_file():
            errors.append(f"npz_concat: path not found: {path_field}")
        if isinstance(paths_field, dict):
            for phase, p in paths_field.items():
                if not Path(p).is_file():
                    errors.append(f"npz_concat: paths.{phase} not found: {p}")

        for phase in ('train', 'val'):
            phase_cfg = config.get(phase)
            if phase_cfg is None:
                continue
            if not isinstance(phase_cfg, dict):
                errors.append(f"npz_concat.{phase} must be a dict")
                continue
            if not isinstance(phase_cfg.get('key'), str):
                errors.append(f"npz_concat.{phase}.key is required and must be a string")
            runs = phase_cfg.get('runs')
            if not isinstance(runs, dict) or not runs:
                errors.append(
                    f"npz_concat.{phase}.runs must be a non-empty dict "
                    "of {run_name: row_count}"
                )

        if config.get('train') is None and config.get('val') is None:
            errors.append("npz_concat requires at least one of 'train' or 'val' blocks")
        return errors


def _load_phase_array(config: dict, phase: str, phase_cfg: dict) -> np.ndarray:
    """Open the .npz for *phase* and return the raw 2-D array."""
    paths_field = config.get('paths')
    if isinstance(paths_field, dict) and phase in paths_field:
        npz_path = Path(paths_field[phase])
    else:
        npz_path = Path(config['path'])

    key = phase_cfg['key']
    with np.load(npz_path) as npz:
        if key not in npz:
            raise KeyError(
                f"npz_concat: key '{key}' not in {npz_path} "
                f"(available: {list(npz.keys())})"
            )
        arr = npz[key]

    if arr.ndim == 3:
        # Validation arrays often arrive as (k_repeats, T, D); collapse
        # the leading dim via ``repeat`` (int index) or 'mean'.
        repeat = phase_cfg.get('repeat', 0)
        if repeat == 'mean':
            arr = arr.mean(axis=0)
        else:
            arr = arr[int(repeat)]
    if arr.ndim != 2:
        raise ValueError(
            f"npz_concat.{phase}.key='{phase_cfg['key']}' must be 2-D after "
            f"collapsing repeats; got shape {arr.shape}"
        )
    return arr


def _split_phase(arr: np.ndarray, phase_cfg: dict) -> dict[str, np.ndarray]:
    """Slice *arr* (T_concat, D) into per-run blocks using
    ``phase_cfg['runs']`` as an ordered {run_name: row_count} map."""
    runs: dict[str, Any] = phase_cfg['runs']
    total_rows = sum(int(n) for n in runs.values())
    if total_rows != arr.shape[0]:
        raise ValueError(
            f"npz_concat: declared run lengths sum to {total_rows} rows "
            f"but the array has {arr.shape[0]} rows (key='{phase_cfg['key']}')"
        )
    blocks: dict[str, np.ndarray] = {}
    start = 0
    for run_name, length in runs.items():
        end = start + int(length)
        blocks[run_name] = arr[start:end]
        start = end
    return blocks
