"""Pipeline runs: list, detail (+ live node status), cancel, resume, restart, delete, events, log."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(tags=["preproc-runs"])


def _manager(request: Request):
    return request.app.state.preproc_run_manager


def _get(request: Request, run_id: str) -> dict:
    summary = _manager(request).get_run(run_id)
    if summary is None:
        raise HTTPException(404, detail=f"run {run_id!r} not found")
    return summary


@router.get("/preproc/runs")
async def list_runs(request: Request):
    runs = _manager(request).list_runs()
    runs.sort(key=lambda r: r.get("started_at") or 0, reverse=True)
    return {"runs": runs}


@router.get("/preproc/runs/{run_id}")
async def get_run(request: Request, run_id: str, nipype: bool = Query(True)):
    summary = _get(request, run_id)
    if nipype:
        summary["nipype_status"] = _manager(request).nipype_status(run_id)
    summary["job"] = _manager(request).job(run_id)
    return summary


@router.get("/preproc/runs/{run_id}/events")
async def run_events(request: Request, run_id: str, offset: int = Query(0, ge=0)):
    """Poll-style access to ``events.jsonl`` (the WebSocket streams the same file)."""
    _get(request, run_id)
    path = _manager(request).events_path(run_id)
    events: list[dict] = []
    new_offset = offset
    if path.is_file():
        with open(path, "r", encoding="utf-8") as f:
            f.seek(offset)
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
            new_offset = f.tell()
    return {"events": events, "offset": new_offset}


@router.get("/preproc/runs/{run_id}/log")
async def run_log(request: Request, run_id: str, tail: int = Query(200, ge=1, le=5000)):
    _get(request, run_id)
    path = _manager(request).registry.stdout_path(run_id)
    if not Path(path).is_file():
        return {"lines": []}
    lines = Path(path).read_text(errors="replace").splitlines()
    return {"lines": lines[-tail:], "total": len(lines)}


@router.get("/preproc/runs/{run_id}/crashes")
async def run_crashes(request: Request, run_id: str):
    """nipype crash dumps written for this run."""
    _get(request, run_id)
    return {"crashes": _manager(request).crash_files(run_id)}


@router.get("/preproc/runs/{run_id}/crashes/{name}")
async def run_crash(request: Request, run_id: str, name: str):
    _get(request, run_id)
    text = _manager(request).read_crash(run_id, name)
    if text is None:
        raise HTTPException(status_code=404, detail=f"no crash file {name!r} for run {run_id}")
    return {"name": name, "text": text}


@router.get("/preproc/runs/{run_id}/checkpoints")
async def run_checkpoints(request: Request, run_id: str):
    _get(request, run_id)
    mgr = _manager(request)
    return {"checkpoints": mgr.checkpoints(run_id), "summary": mgr.checkpoint_summary(run_id)}


@router.get("/preproc/runs/{run_id}/checkpoints/{index}/thumbnail")
async def run_checkpoint_thumbnail(request: Request, run_id: str, index: int):
    from fastapi.responses import FileResponse
    from fmriflow.preproc.checkpoints import render_thumbnail

    _get(request, run_id)
    cps = _manager(request).checkpoints(run_id)
    if index < 0 or index >= len(cps):
        raise HTTPException(404, detail="no such checkpoint")
    artifact = cps[index].get("artifact")
    png = render_thumbnail(Path(artifact)) if artifact else None
    if png is None:
        raise HTTPException(404, detail="no thumbnail for this checkpoint")
    return FileResponse(str(png), media_type="image/png")


@router.post("/preproc/runs/{run_id}/cancel")
async def cancel_run(request: Request, run_id: str):
    _get(request, run_id)
    return _manager(request).cancel_run(run_id)


@router.post("/preproc/runs/{run_id}/resume")
async def resume_run(request: Request, run_id: str):
    _get(request, run_id)
    try:
        new_id = _manager(request).resume_run(run_id)
    except (KeyError, ValueError) as e:
        raise HTTPException(409, detail=str(e))
    return {"run_id": new_id, "resumed_from": run_id}


@router.post("/preproc/runs/{run_id}/restart")
async def restart_run(request: Request, run_id: str):
    _get(request, run_id)
    try:
        new_id = _manager(request).restart_run(run_id)
    except (KeyError, ValueError) as e:
        raise HTTPException(409, detail=str(e))
    return {"run_id": new_id, "restarted_from": run_id}


@router.delete("/preproc/runs/{run_id}")
async def delete_run(request: Request, run_id: str):
    _get(request, run_id)
    try:
        deleted = _manager(request).delete_run(run_id)
    except ValueError as e:
        raise HTTPException(409, detail=str(e))
    return {"deleted": deleted}
