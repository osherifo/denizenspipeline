"""Saved per-subject values, so a resumed group run can still use finished subjects.

"Light" values are the model result plus ``analysis.*`` and ``external.*`` keys:
what group analyzers usually read, without raw stimuli, responses, features or
prepared matrices. They are saved next to the subject's run summary and only
loaded back for the same resolved subject config.
"""

from __future__ import annotations

import hashlib
import json
import logging
import pickle
from pathlib import Path
from typing import Any

from fmriflow.context import PipelineContext

logger = logging.getLogger(__name__)

VALUES_DIR = ".values"
VALUES_FILE = "context.pkl"
LIGHT_KEYS: tuple[str, ...] = ("result",)
LIGHT_PREFIXES: tuple[str, ...] = ("analysis.", "external.")


def values_path(run_dir: Path | str) -> Path:
    return Path(run_dir) / VALUES_DIR / VALUES_FILE


def config_fingerprint(config: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(config, sort_keys=True, default=str).encode()).hexdigest()


def light_values(ctx: PipelineContext) -> dict[str, Any]:
    return {k: v for k, v in ctx._store.items() if k in LIGHT_KEYS or k.startswith(LIGHT_PREFIXES)}


def save_light_values(ctx: PipelineContext, config: dict[str, Any], run_dir: Path | str) -> Path | None:
    """Save ``ctx``'s light values for ``config``; ``None`` (with a warning) when that fails."""
    path = values_path(run_dir)
    tmp = path.with_suffix(".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "wb") as f:
            pickle.dump({"fingerprint": config_fingerprint(config), "values": light_values(ctx)}, f)
        tmp.replace(path)
        return path
    except Exception:
        logger.warning("Could not save resume values under %s", run_dir, exc_info=True)
        tmp.unlink(missing_ok=True)
        return None


def load_light_values(config: dict[str, Any], run_dir: Path | str) -> PipelineContext | None:
    """A context holding the saved light values, or ``None`` when there are none for this config.

    The returned context has ``restored_values = True``: it is enough for group
    analyzers, not for re-running a subject's stages.
    """
    path = values_path(run_dir)
    if not path.is_file():
        return None
    try:
        with open(path, "rb") as f:
            payload = pickle.load(f)
    except Exception:
        logger.warning("Could not read resume values %s", path, exc_info=True)
        return None
    if payload.get("fingerprint") != config_fingerprint(config):
        logger.warning("Resume values %s were saved for a different subject config; not using them", path)
        return None
    ctx = PipelineContext(config)
    for key, value in (payload.get("values") or {}).items():
        ctx.put(key, value)
    ctx.restored_values = True
    return ctx
