"""Experimental, decoupled Claude AI assistant for fMRIflow.

Everything AI-specific lives in this package. It is **off by default**,
gated behind the ``AGENT_ENABLED`` setting, and imports the optional
``anthropic`` dependency lazily (only when a session actually runs), so
the rest of the app has no import-time coupling to it.

The assistant is **advisory only**: it reads context through read-only
tools (:mod:`fmriflow.agent.tools`) and answers in chat. It never writes
files or mutates app state.

Remove the whole feature by deleting this package plus the handful of
gated call-sites in ``server/app.py``, ``server/ws.py``,
``server/routes/agent.py``, ``server/routes/settings.py`` and
``core/paths.py``.
"""

from __future__ import annotations

from fmriflow.agent.manager import AgentSessionManager

__all__ = ["AgentSessionManager"]
