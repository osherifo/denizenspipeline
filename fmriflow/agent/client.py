"""Anthropic client + model/key resolution for the assistant.

The ``anthropic`` SDK is an **optional** dependency (the ``agent`` extra).
It is imported lazily here so importing this module never fails on a base
install — only :func:`get_async_client` requires the package present.
"""

from __future__ import annotations

from fmriflow.core import paths


class AgentUnavailable(RuntimeError):
    """Raised when the assistant can't run (disabled / no key / no SDK)."""


def resolve_model() -> str:
    return paths.agent_model()


def get_async_client():
    """Return a configured ``anthropic.AsyncAnthropic`` client.

    Raises :class:`AgentUnavailable` with a user-facing message if the
    assistant is disabled, no API key is configured, or the ``anthropic``
    package is not installed.
    """
    if not paths.agent_enabled():
        raise AgentUnavailable("The AI assistant is turned off. Enable it in Settings.")

    key = paths.anthropic_api_key()
    if not key:
        raise AgentUnavailable(
            "No Claude API key configured. Set ANTHROPIC_API_KEY or add a key in Settings."
        )

    try:
        import anthropic
    except ImportError as e:  # pragma: no cover - depends on optional extra
        raise AgentUnavailable(
            "The 'anthropic' package is not installed. Install the assistant extra: "
            "pip install -e '.[agent]'"
        ) from e

    return anthropic.AsyncAnthropic(api_key=key)
