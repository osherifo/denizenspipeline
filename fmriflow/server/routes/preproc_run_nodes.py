"""One node of one pipeline run, for the run UI's node popup.

Everything here is **run-scoped**: the files served are the ones this run's
node produced (``result.nodes[node_id].outputs``), not "the manifest that
happens to match the subject". Which files a node has is described by its
``ui`` capabilities (:func:`fmriflow.preproc.node_registry.node_ui`) — each
capability names an output port, and the port's value is the path served.

  GET  /preproc/runs/{run_id}/nodes/{node_id}                 record + capabilities
  GET  /preproc/runs/{run_id}/nodes/{node_id}/log?tail=       <node work dir>/stdout.log
  GET  /preproc/runs/{run_id}/nodes/{node_id}/inner?cap=      the node's inner nipype status
  GET  /preproc/runs/{run_id}/nodes/{node_id}/manifest        the node's preproc manifest JSON
  GET  /preproc/runs/{run_id}/nodes/{node_id}/report/{rest}   HTML report (+ its relative assets)
  GET  /preproc/runs/{run_id}/nodes/{node_id}/fs-file?rel=    FreeSurfer subject files
  GET  /preproc/runs/{run_id}/nodes/{node_id}/freeview-command
  POST /preproc/runs/{run_id}/nodes/{node_id}/drawing
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse

from fmriflow.server.services.qc_files import (
    FS_ALLOWED_SUFFIXES,
    OUT_ALLOWED_SUFFIXES,
    build_freeview_command,
    find_fs_subject_dir,
    save_drawing,
    serve_file,
)

router = APIRouter(tags=["preproc-run-nodes"])


# ── helpers ─────────────────────────────────────────────────────────────


def _manager(request: Request):
    return request.app.state.preproc_run_manager


def _run(request: Request, run_id: str) -> dict:
    summary = _manager(request).get_run(run_id)
    if summary is None:
        raise HTTPException(404, f"Run '{run_id}' not found")
    return summary


def _record(request: Request, run_id: str, node_id: str) -> dict[str, Any]:
    """The run's record for one node, merged with what the library knows.

    A node the runner has not reached yet is synthesised as ``pending`` so
    the popup can open on a live run and fill in as events arrive.
    """
    summary = _run(request, run_id)
    job = _manager(request).job(run_id) or {}
    pipeline = job.get("pipeline") or {}
    doc = next((n for n in pipeline.get("nodes") or [] if n.get("id") == node_id), None)
    listed = next((n for n in summary.get("nodes") or [] if n.get("id") == node_id), None)
    result = summary.get("result") if isinstance(summary.get("result"), dict) else {}
    rec = next((n for n in (result.get("nodes") or []) if n.get("node_id") == node_id), None)
    if rec is None and doc is None and listed is None:
        raise HTTPException(404, f"Run '{run_id}' has no node '{node_id}'")

    workflow = summary.get("workflow")
    work_dir = summary.get("work_dir")
    node_type = (rec or {}).get("node_type") or (doc or {}).get("type") or (listed or {}).get("type") or ""
    kind = (rec or {}).get("kind") or (doc or {}).get("kind") or (listed or {}).get("kind") or ""
    node_work_dir = (rec or {}).get("work_dir") or (
        str(Path(work_dir) / workflow / node_id) if work_dir and workflow else None
    )

    registry = request.app.state.node_registry
    try:
        info = registry.info(node_type).to_dict() if node_type else {}
    except KeyError:
        info = {}

    return {
        "run_id": run_id,
        "node_id": node_id,
        "node_type": node_type,
        "kind": kind,
        "status": (rec or {}).get("status") or "pending",
        "duration_s": (rec or {}).get("duration_s"),
        "work_dir": node_work_dir,
        "outputs": dict((rec or {}).get("outputs") or {}),
        "error": (rec or {}).get("error"),
        "params": dict(((doc or {}).get("data") or {}).get("params") or {}),
        "ui": info.get("ui") or {},
        "output_ports": info.get("outputs") or {},
        "params_schema": info.get("params_schema") or {},
        "has_log": bool(node_work_dir and (Path(node_work_dir) / "stdout.log").is_file()),
        "subject": summary.get("subject") or "",
        "dataset": ((job.get("request") or {}).get("dataset")) or None,
        "workflow": workflow,
        "run_status": summary.get("status"),
    }


def _port_path(record: dict[str, Any], capability: str) -> Path:
    port = (record.get("ui") or {}).get(capability)
    if not port:
        raise HTTPException(404, f"node {record['node_id']!r} declares no {capability} view")
    value = record["outputs"].get(port)
    if not value:
        raise HTTPException(404, f"node {record['node_id']!r} has no {port!r} output yet")
    return Path(str(value))


def _fs_dir(record: dict[str, Any]) -> Path:
    root = _port_path(record, "structural_qc")
    fs = find_fs_subject_dir(root, record["subject"], record["outputs"].get("derivatives_dir"))
    if fs is None:
        raise HTTPException(404, "No FreeSurfer subject directory for this node")
    return fs


# ── routes ──────────────────────────────────────────────────────────────


@router.get("/preproc/runs/{run_id}/nodes/{node_id}")
async def get_run_node(request: Request, run_id: str, node_id: str):
    return _record(request, run_id, node_id)


@router.get("/preproc/runs/{run_id}/nodes/{node_id}/log")
async def get_run_node_log(request: Request, run_id: str, node_id: str, tail: int = Query(200, ge=1, le=5000)):
    rec = _record(request, run_id, node_id)
    path = Path(rec["work_dir"]) / "stdout.log" if rec.get("work_dir") else None
    if not path or not path.is_file():
        return {"lines": [], "total": 0}
    lines = path.read_text(errors="replace").splitlines()
    return {"lines": lines[-tail:], "total": len(lines)}


@router.get("/preproc/runs/{run_id}/nodes/{node_id}/inner")
async def get_run_node_inner(request: Request, run_id: str, node_id: str, cap: int = Query(500, ge=1, le=2000)):
    """The node's own inner nipype status (fmriprep's workflow, say), with
    the ``<workflow>.<node_id>.`` prefix stripped so the subtree root is the
    app's own top-level workflow."""
    from fmriflow.preproc.nipype_log import parse_nipype_events_file, reconcile_with_run_state

    rec = _record(request, run_id, node_id)
    prefix = f"{rec['workflow']}.{node_id}." if rec.get("workflow") else f"{node_id}."
    block = parse_nipype_events_file(_manager(request).events_path(run_id), cap=cap, prefix=prefix)
    state = _manager(request).registry.load(run_id)
    if state is not None:
        block = reconcile_with_run_state(block, run_status=_manager(request)._live_status(state))
    return {"prefix": prefix, "nipype_status": block.to_dict()}


@router.get("/preproc/runs/{run_id}/nodes/{node_id}/manifest")
async def get_run_node_manifest(request: Request, run_id: str, node_id: str):
    path = _port_path(_record(request, run_id, node_id), "summary")
    if not path.is_file():
        raise HTTPException(404, f"manifest not found: {path}")
    try:
        return json.loads(path.read_text())
    except ValueError as e:
        raise HTTPException(500, f"manifest is not valid JSON: {e}")


@router.get("/preproc/runs/{run_id}/nodes/{node_id}/report/{rest:path}")
async def get_run_node_report(request: Request, run_id: str, node_id: str, rest: str = ""):
    """The node's HTML report at ``…/report/``; any other path under it is
    one of the report's relative assets, served from the report's folder."""
    report = _port_path(_record(request, run_id, node_id), "report")
    if not rest:
        if not report.is_file():
            raise HTTPException(404, f"report not found: {report}")
        return FileResponse(report, media_type="text/html")
    return serve_file(report.parent, rest, OUT_ALLOWED_SUFFIXES)


@router.get("/preproc/runs/{run_id}/nodes/{node_id}/fs-file")
async def get_run_node_fs_file(request: Request, run_id: str, node_id: str, rel: str):
    return serve_file(_fs_dir(_record(request, run_id, node_id)), rel, FS_ALLOWED_SUFFIXES, media_types={})


@router.get("/preproc/runs/{run_id}/nodes/{node_id}/freeview-command")
async def get_run_node_freeview(request: Request, run_id: str, node_id: str):
    fs = _fs_dir(_record(request, run_id, node_id))
    return {"command": build_freeview_command(fs), "fs_subject_dir": str(fs)}


@router.post("/preproc/runs/{run_id}/nodes/{node_id}/drawing")
async def post_run_node_drawing(
    request: Request, run_id: str, node_id: str,
    file: UploadFile = File(...),
    ras_x: float = Query(0.0), ras_y: float = Query(0.0), ras_z: float = Query(0.0),
):
    fs = _fs_dir(_record(request, run_id, node_id))
    return save_drawing(fs, await file.read(), (ras_x, ras_y, ras_z))
