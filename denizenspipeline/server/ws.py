"""WebSocket handler for live run streaming."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


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
