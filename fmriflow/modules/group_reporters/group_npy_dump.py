"""Persist numeric group artifacts to disk as ``.npy`` / JSON.

``GroupResult.artifacts`` lives in memory; the group summary JSON records
their shape but not the values. This reporter writes every ndarray and
scalar/dict artifact next to ``group_summary.json`` so users can load
them in a notebook or hand them off to downstream tooling.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import numpy as np

from fmriflow.core.group_types import GroupResult
from fmriflow.core.types import SemanticSubspace
from fmriflow.modules._decorators import group_reporter
from fmriflow.modules.group_analyzers._helpers import my_cfg

logger = logging.getLogger(__name__)


@group_reporter("group_npy_dump")
class GroupNpyDumpReporter:
    """Save group artifacts under ``<output_dir>/group_artifacts/``.

    - ndarrays → ``<safe_key>.npy``
    - :class:`SemanticSubspace` → ``<safe_key>.npy`` (basis) + ``<safe_key>.json``
      (singular values, feature, n_delays, feature_dim, metadata)
    - scalars / dicts / lists → coalesced into ``scalars.json``

    Keys are sanitised (``/`` → ``_``) to keep flat filenames.
    """

    name = "group_npy_dump"
    PARAM_SCHEMA = {
        "output_dir": {
            "type": "str",
            "description": (
                "Where to write the dump. Defaults to "
                "'<group output_dir>/group_artifacts/'."
            ),
        },
    }

    def report(self, group: GroupResult, config: dict) -> dict[str, str]:
        cfg = my_cfg(config, self.name)
        base_str = cfg.get("output_dir") or config.get("output_dir")
        base = Path(base_str).resolve() if base_str else Path.cwd()
        outdir = base / "group_artifacts"
        outdir.mkdir(parents=True, exist_ok=True)

        scalars: dict[str, Any] = {}
        saved: dict[str, str] = {}

        for key, value in group.artifacts.items():
            safe = _safe_key(key)
            if isinstance(value, np.ndarray):
                path = outdir / f"{safe}.npy"
                np.save(path, value)
                saved[key] = str(path)
            elif isinstance(value, SemanticSubspace):
                npy_path = outdir / f"{safe}.npy"
                np.save(npy_path, value.basis)
                meta_path = outdir / f"{safe}.json"
                meta_path.write_text(json.dumps({
                    "singular_values": value.singular_values.tolist(),
                    "feature": value.feature,
                    "n_delays": value.n_delays,
                    "feature_dim": value.feature_dim,
                    "n_components": value.n_components,
                    "metadata": _jsonable(value.metadata),
                }, indent=2))
                saved[key] = str(npy_path)
                saved[f"{key}.meta"] = str(meta_path)
            else:
                scalars[key] = _jsonable(value)

        if scalars:
            scalars_path = outdir / "scalars.json"
            scalars_path.write_text(json.dumps(scalars, indent=2))
            saved["__scalars__"] = str(scalars_path)

        return saved

    def validate_config(self, config: dict) -> list[str]:
        return []


# ─── helpers ───────────────────────────────────────────────────

_KEY_SAFE = re.compile(r"[^A-Za-z0-9._-]")


def _safe_key(key: str) -> str:
    return _KEY_SAFE.sub("_", key)


def _jsonable(value: Any) -> Any:
    """Convert numpy types / nested arrays into JSON-encodable values."""
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value
