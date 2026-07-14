"""WebSocket handler for live run streaming."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from fmriflow.core import paths

router = APIRouter()

logger = logging.getLogger(__name__)


@router.websocket("/ws/agent/{session_id}")
async def agent_websocket(websocket: WebSocket, session_id: str):
    """Bidirectional chat with the experimental AI assistant.

    The client sends ``{mode, message, context}`` JSON frames; for each,
    the server streams back ``{type: 'delta'|'tool'|'done'|'error', ...}``
    events for that turn, then waits for the next message. The socket
    stays open for the whole conversation (multi-turn).
    """
    manager = getattr(websocket.app.state, "agent_manager", None)
    if manager is None or not paths.agent_enabled():
        await websocket.close(code=4003, reason="AI assistant is disabled")
        return

    await websocket.accept()
    try:
        while True:
            payload = await websocket.receive_json()
            mode = payload.get("mode", "generic")
            message = payload.get("message", "")
            context = payload.get("context")
            if not message:
                continue
            async for event in manager.stream(
                session_id, mode, message, context, websocket.app.state
            ):
                await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await websocket.close()
        except Exception:
            pass


@router.websocket("/ws/runs/{run_id}")
async def run_websocket(websocket: WebSocket, run_id: str):
    """Stream live events from a running pipeline via WebSocket."""
    manager = websocket.app.state.run_manager
    handle = manager.active_runs.get(run_id)

    if handle is None:
        await websocket.close(code=4004, reason=f"Run '{run_id}' not found")
        return

    await websocket.accept()

    try:
        # Send any events that already happened before connection
        for event in handle.events:
            await websocket.send_json(event)

        # Poll for new events until the run completes
        while handle.status == 'running':
            new_events = handle.drain_events()
            for event in new_events:
                await websocket.send_json(event)

            if not new_events:
                await asyncio.sleep(0.2)

        # Drain any final events
        final_events = handle.drain_events()
        for event in final_events:
            await websocket.send_json(event)

        # Send terminal event
        if handle.status == 'done':
            await websocket.send_json({'event': 'run_done'})
        elif handle.status == 'failed':
            await websocket.send_json({
                'event': 'run_failed',
                'error': handle.error,
            })

    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await websocket.close()
        except Exception:
            pass


@router.websocket("/ws/preproc/{run_id}")
async def preproc_websocket(websocket: WebSocket, run_id: str):
    """Stream live events from a running preprocessing job."""
    manager = websocket.app.state.preproc_manager
    handle = manager.active_runs.get(run_id)

    if handle is None:
        await websocket.close(code=4004, reason=f"Preproc run '{run_id}' not found")
        return

    await websocket.accept()

    try:
        for event in handle.events:
            await websocket.send_json(event)

        while handle.status == 'running':
            new_events = handle.drain_events()
            for event in new_events:
                await websocket.send_json(event)
            if not new_events:
                await asyncio.sleep(0.3)

        final_events = handle.drain_events()
        for event in final_events:
            await websocket.send_json(event)

    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await websocket.close()
        except Exception:
            pass


@router.websocket("/ws/preproc/stack/{run_id}")
async def stack_websocket(websocket: WebSocket, run_id: str):
    """Stream events from a detached PreprocStack run.

    The CLI shim writes events to ``<run_dir>/events.jsonl``; this
    handler tails the file by tracking byte offset. On connect we
    replay any events that already exist (for late subscribers),
    then poll for new ones until the run leaves ``running`` state.
    Finally we send one ``_close`` event carrying the terminal
    status before closing the socket.
    """
    manager = websocket.app.state.stack_manager
    state = manager.registry.load(run_id)

    if state is None:
        await websocket.close(code=4004, reason=f"Stack run '{run_id}' not found")
        return

    events_path = manager.registry.run_dir(run_id) / "events.jsonl"

    await websocket.accept()

    def _stream_from(offset: int) -> tuple[int, list[dict]]:
        """Read new lines from events_path starting at ``offset``.
        Returns (new_offset, parsed_events). Malformed lines are
        skipped with a warning — never break the WS stream.
        """
        events: list[dict] = []
        if not events_path.is_file():
            return offset, events
        try:
            with open(events_path, "r", encoding="utf-8") as f:
                f.seek(offset)
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        logger.warning(
                            "Malformed event in %s: %r", events_path, line,
                        )
                new_offset = f.tell()
        except OSError as e:
            logger.warning("Could not read %s: %s", events_path, e)
            return offset, events
        return new_offset, events

    offset = 0
    try:
        # Initial replay of whatever's already on disk.
        offset, replay = _stream_from(offset)
        for ev in replay:
            await websocket.send_json(ev)

        # Live tail until the run reaches a terminal state.
        while True:
            current = manager.registry.load(run_id)
            # PID liveness reconciliation — if the subprocess died
            # without writing a terminal status to state.json, the
            # registry still says "running" indefinitely. Mirror the
            # same check :meth:`StackManager.get_run` performs so the
            # socket closes reliably on a crashed run.
            live_status = current.status if current else "lost"
            if (
                current is not None
                and current.status == "running"
                and not manager.registry.pid_alive(current.pid)
            ):
                live_status = "lost"

            terminal = current is None or live_status not in ("running",)

            offset, new = _stream_from(offset)
            for ev in new:
                await websocket.send_json(ev)

            if terminal:
                await websocket.send_json({
                    "event": "_close",
                    "status": live_status,
                })
                break

            if not new:
                await asyncio.sleep(0.2)

    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await websocket.close()
        except Exception:
            pass


@router.websocket("/ws/autoflatten/{run_id}")
async def autoflatten_websocket(websocket: WebSocket, run_id: str):
    """Stream live events from a running autoflatten job."""
    manager = websocket.app.state.autoflatten_manager
    handle = manager.active_runs.get(run_id)

    if handle is None:
        await websocket.close(code=4004, reason=f"Autoflatten run '{run_id}' not found")
        return

    await websocket.accept()

    try:
        for event in handle.events:
            await websocket.send_json(event)

        while handle.status == 'running':
            new_events = handle.drain_events()
            for event in new_events:
                await websocket.send_json(event)
            if not new_events:
                await asyncio.sleep(0.3)

        final_events = handle.drain_events()
        for event in final_events:
            await websocket.send_json(event)

    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await websocket.close()
        except Exception:
            pass


@router.websocket("/ws/convert/batch/{batch_id}")
async def convert_batch_websocket(websocket: WebSocket, batch_id: str):
    """Stream live events from a batch DICOM-to-BIDS conversion."""
    manager = websocket.app.state.convert_manager
    handle = manager.active_batches.get(batch_id)

    if handle is None:
        await websocket.close(code=4004, reason=f"Batch '{batch_id}' not found")
        return

    await websocket.accept()

    try:
        # Send historical events
        with handle._lock:
            for event in handle.events:
                await websocket.send_json(event)

        # Poll for new events
        while handle.status == 'running':
            new_events = handle.drain_events()
            for event in new_events:
                await websocket.send_json(event)
            if not new_events:
                await asyncio.sleep(0.3)

        # Drain final events
        final_events = handle.drain_events()
        for event in final_events:
            await websocket.send_json(event)

    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await websocket.close()
        except Exception:
            pass


@router.websocket("/ws/convert/{run_id}")
async def convert_websocket(websocket: WebSocket, run_id: str):
    """Stream live events from a running DICOM-to-BIDS conversion."""
    manager = websocket.app.state.convert_manager
    handle = manager.active_runs.get(run_id)

    if handle is None:
        await websocket.close(code=4004, reason=f"Convert run '{run_id}' not found")
        return

    await websocket.accept()

    try:
        for event in handle.events:
            await websocket.send_json(event)

        while handle.status == 'running':
            new_events = handle.drain_events()
            for event in new_events:
                await websocket.send_json(event)
            if not new_events:
                await asyncio.sleep(0.3)

        final_events = handle.drain_events()
        for event in final_events:
            await websocket.send_json(event)

    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await websocket.close()
        except Exception:
            pass
