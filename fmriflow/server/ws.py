"""WebSocket handler for live run streaming."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

logger = logging.getLogger(__name__)


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


async def _tail_events_jsonl(websocket: WebSocket, registry, run_id: str, events_path) -> None:
    """Replay + live-tail ``events.jsonl`` for a detached run until it leaves ``running``.

    Shared by the pipeline and (legacy) stack sockets. Sends one ``_close``
    event carrying the terminal status before returning.
    """
    def _stream_from(offset: int) -> tuple[int, list[dict]]:
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
                        ev = json.loads(line)
                    except json.JSONDecodeError:
                        logger.warning("Malformed event in %s: %r", events_path, line)
                        continue
                    if ev.get("event") == "checkpoint":
                        from fmriflow.preproc.checkpoints import is_parked_record, trim_record
                        if is_parked_record(ev):
                            continue
                        ev = trim_record(ev)
                    events.append(ev)
                new_offset = f.tell()
        except OSError as e:
            logger.warning("Could not read %s: %s", events_path, e)
            return offset, events
        return new_offset, events

    offset = 0
    try:
        offset, replay = _stream_from(offset)
        for ev in replay:
            await websocket.send_json(ev)
        while True:
            current = registry.load(run_id)
            live_status = current.status if current else "lost"
            if current is not None and current.status == "running" and not registry.pid_alive(current.pid):
                live_status = "lost"
            terminal = current is None or live_status != "running"
            offset, new = _stream_from(offset)
            for ev in new:
                await websocket.send_json(ev)
            if terminal:
                await websocket.send_json({"event": "_close", "status": live_status})
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


@router.websocket("/ws/preproc/{run_id}")
async def preproc_websocket(websocket: WebSocket, run_id: str):
    """Stream a pipeline run's ``events.jsonl``: replay, then live tail."""
    manager = websocket.app.state.preproc_run_manager
    if manager.get_run(run_id) is None:
        await websocket.close(code=4004, reason=f"Preproc run '{run_id}' not found")
        return
    await websocket.accept()
    await _tail_events_jsonl(websocket, manager.registry, run_id, manager.events_path(run_id))


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
