"""Agent session manager — holds per-session history and streams turns.

Lives on ``app.state.agent_manager``. One instance per server; conversation
history is keyed by ``session_id`` so a reconnect resumes the same chat.

:meth:`stream` runs a manual, streaming agentic loop: it streams the
assistant's text deltas out, and whenever the model requests a read-only
tool it executes it against the live ``app.state`` and feeds the result
back — looping until the model stops calling tools.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from fmriflow.agent import client as agent_client
from fmriflow.agent import modes as agent_modes
from fmriflow.agent import tools as agent_tools

logger = logging.getLogger(__name__)

_MAX_TOKENS = 8192
_MAX_TOOL_ROUNDS = 8       # guard against runaway tool loops
_MAX_HISTORY_MESSAGES = 40  # trim old turns to bound context


class AgentSessionManager:
    """Owns conversation state and drives streaming turns for the assistant."""

    def __init__(self) -> None:
        self._histories: dict[str, list[dict]] = {}

    def reset(self, session_id: str) -> None:
        self._histories.pop(session_id, None)

    async def stream(
        self,
        session_id: str,
        mode: str,
        message: str,
        context: dict | None,
        state: Any,
    ) -> AsyncIterator[dict]:
        """Yield event dicts for one user turn.

        Event shapes: ``{"type": "delta", "text": ...}`` (streamed text),
        ``{"type": "tool", "name": ...}`` (a tool is being called),
        ``{"type": "done"}`` (turn complete), ``{"type": "error", ...}``.
        """
        client = agent_client.get_async_client()  # raises AgentUnavailable
        model = agent_client.resolve_model()
        system = agent_modes.system_prompt(mode)
        tool_specs = agent_modes.tool_specs(mode)

        history = self._histories.setdefault(session_id, [])

        # First message of a session gets the view's opening context.
        user_text = message
        if not history:
            preamble = agent_modes.build_opening(mode, context)
            if preamble:
                user_text = f"{preamble}\n\n{message}"
        history.append({"role": "user", "content": user_text})

        try:
            for _ in range(_MAX_TOOL_ROUNDS):
                async with client.messages.stream(
                    model=model,
                    max_tokens=_MAX_TOKENS,
                    system=system,
                    tools=tool_specs,
                    messages=history,
                ) as stream:
                    async for text in stream.text_stream:
                        yield {"type": "delta", "text": text}
                    final = await stream.get_final_message()

                history.append({"role": "assistant", "content": final.content})

                if final.stop_reason != "tool_use":
                    break

                tool_results = []
                for block in final.content:
                    if getattr(block, "type", None) != "tool_use":
                        continue
                    yield {"type": "tool", "name": block.name}
                    result = agent_tools.run_tool(block.name, dict(block.input or {}), state)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
                history.append({"role": "user", "content": tool_results})
            else:
                yield {"type": "delta", "text": "\n\n_(stopped: too many tool calls)_"}

            self._trim(session_id)
            yield {"type": "done"}
        except Exception as e:  # noqa: BLE001 - report to the client, keep server alive
            logger.warning("Agent stream failed (session %s): %s", session_id, e)
            yield {"type": "error", "message": str(e)}

    def _trim(self, session_id: str) -> None:
        h = self._histories.get(session_id)
        if h and len(h) > _MAX_HISTORY_MESSAGES:
            self._histories[session_id] = h[-_MAX_HISTORY_MESSAGES:]
