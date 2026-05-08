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

from fastapi import APIRouter
from pydantic import BaseModel

from fmriflow.core import paths

logger = logging.getLogger(__name__)
router = APIRouter(tags=["settings"], prefix="/settings")


class SettingsUpdate(BaseModel):
    """Writable runtime overrides. Empty string clears the override."""

    FMRIFLOW_HOME: str | None = None
    FMRIFLOW_DATA: str | None = None
    FS_LICENSE: str | None = None
    FMRIFLOW_SINGULARITY_BIN: str | None = None


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
    payload = update.model_dump()
    paths.save_runtime_config(payload)
    snap = paths.settings_snapshot()
    snap["restart_required"] = True
    return snap
