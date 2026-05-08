"""Settings endpoints — read and persist runtime path overrides.

The Settings tab in the frontend writes a small JSON file at
``~/.config/fmriflow/settings.json``. ``fmriflow.core.paths``
consults it as a fallback below env vars, so explicit shell
exports always win.

Saved values do **not** apply live — services cache resolved paths
at startup. The UI shows a "restart required" banner after a
successful POST.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from fmriflow.core import paths

logger = logging.getLogger(__name__)
router = APIRouter(tags=["settings"], prefix="/settings")

# Keys whose value is a directory path. The other writable keys
# (``FS_LICENSE``, ``FMRIFLOW_SINGULARITY_BIN``) point at files
# and aren't safe to mkdir.
_DIR_KEYS = ("FMRIFLOW_HOME", "FMRIFLOW_DATA")


class SettingsUpdate(BaseModel):
    """Writable runtime overrides. Empty string clears the override.

    If ``create_missing`` is true, the backend will ``mkdir -p``
    each directory-shaped path that doesn't yet exist before
    persisting.
    """

    FMRIFLOW_HOME: str | None = None
    FMRIFLOW_DATA: str | None = None
    FS_LICENSE: str | None = None
    FMRIFLOW_SINGULARITY_BIN: str | None = None
    create_missing: bool = False


@router.get("")
def get_settings() -> dict:
    """Return the current settings snapshot (resolved paths + sources)."""
    return paths.settings_snapshot()


@router.post("")
def post_settings(update: SettingsUpdate) -> dict:
    """Persist the supplied overrides to ``~/.config/fmriflow/settings.json``.

    Returns the new snapshot. The caller should display a
    ``restart required`` banner — the running server does not pick
    up the new values until it restarts.
    """
    payload = update.model_dump(exclude={"create_missing"})
    created: list[str] = []
    if update.create_missing:
        for key in _DIR_KEYS:
            value = payload.get(key)
            if not value:
                continue
            p = Path(str(value)).expanduser()
            if not p.exists():
                try:
                    p.mkdir(parents=True, exist_ok=True)
                    created.append(str(p))
                except OSError as e:
                    logger.warning("Could not create %s: %s", p, e)
    paths.save_runtime_config(payload)
    snap = paths.settings_snapshot()
    snap["restart_required"] = True
    snap["created"] = created
    return snap
