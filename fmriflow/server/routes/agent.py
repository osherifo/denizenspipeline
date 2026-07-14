"""Experimental AI assistant — status endpoint.

The chat itself streams over the ``/ws/agent/{session_id}`` WebSocket
(see ``server/ws.py``). This REST route only reports availability so the
frontend can decide whether to render the assistant at all.
"""

from __future__ import annotations

import importlib.util

from fastapi import APIRouter

from fmriflow.agent import modes as agent_modes
from fmriflow.core import paths

router = APIRouter(tags=["agent"], prefix="/agent")


@router.get("/status")
def agent_status() -> dict:
    """Report whether the assistant is enabled, keyed, and installed."""
    snap = paths.agent_snapshot()
    snap["available"] = importlib.util.find_spec("anthropic") is not None
    snap["modes"] = agent_modes.mode_list()
    # `ready` is the single flag the frontend gates the launcher on.
    snap["ready"] = bool(snap["enabled"] and snap["has_key"] and snap["available"])
    return snap
