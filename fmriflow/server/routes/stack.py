"""API routes for the unified PreprocStack runner.

New endpoints live under ``/api/preproc/stack/...`` and
``/api/preproc/backends/...`` and sit alongside the existing
single-backend preproc routes. The legacy routes keep working
unchanged during the transition (Phase 7 will retire them once
the frontend lands).

Frontend-facing surface:

- ``GET  /api/preproc/backends/workflows`` — list registered
  nipype bootstrap workflows (built-in + user + pip).
- ``GET  /api/preproc/backends/workflows/{name}/preflight`` —
  REQUIRED_PYTHON / REQUIRED_TOOLS / REQUIRED_ENV check, so the
  form can render "ready" / "missing FSL" before launch.
- ``GET  /api/preproc/backends/transforms`` — same, for
  transforms.
- ``GET  /api/preproc/backends/transforms/{name}/preflight``.
- ``POST /api/preproc/stack/run`` — launch a stack run.
- ``GET  /api/preproc/stack/runs`` — list every stack run on
  disk.
- ``GET  /api/preproc/stack/{run_id}/status`` — status + result
  summary.
- ``GET  /api/preproc/stack/{run_id}/manifest`` — final
  ``PreprocManifest`` JSON.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from fmriflow.preproc.preflight import preflight
from fmriflow.preproc.stack import (
    BootstrapStage,
    PreprocStack,
    TransformStage,
)

router = APIRouter(tags=["preproc-stack"])


# ── Request models ────────────────────────────────────────────────


class BootstrapStageBody(BaseModel):
    kind: str
    workflow: str | None = None
    params: dict = {}


class TransformStageBody(BaseModel):
    name: str
    params: dict = {}


class StackRunBody(BaseModel):
    """Launch request — combines a stack recipe with a run binding."""

    stack: dict  # Validated downstream by PreprocStack.from_dict
    subject: str
    output_dir: str
    bids_dir: str | None = None
    derivatives_dir: str | None = None
    dataset: str = "unknown"
    sessions: list[str] = []
    task: str | None = None
    use_cache: bool = True


# ── Backend (workflow + transform) listings ───────────────────────


@router.get("/preproc/backends/workflows")
async def list_workflows(request: Request):
    """List registered bootstrap workflows + their declared metadata."""
    reg = request.app.state.workflow_registry
    return {"workflows": [_info_to_dict(info) for info in reg.list()]}


@router.get("/preproc/backends/workflows/{name}/preflight")
async def workflow_preflight(request: Request, name: str):
    reg = request.app.state.workflow_registry
    try:
        workflow = reg.get(name)
    except KeyError:
        raise HTTPException(404, detail=f"Unknown workflow: '{name}'")
    result = preflight(workflow)
    return {
        "ok": result.ok,
        "errors": list(result.errors),
        "warnings": list(result.warnings),
    }


@router.get("/preproc/backends/transforms")
async def list_transforms(request: Request):
    reg = request.app.state.transform_registry
    return {"transforms": [_info_to_dict(info) for info in reg.list()]}


@router.get("/preproc/backends/transforms/{name}/preflight")
async def transform_preflight(request: Request, name: str):
    reg = request.app.state.transform_registry
    try:
        transform = reg.get(name)
    except KeyError:
        raise HTTPException(404, detail=f"Unknown transform: '{name}'")
    result = preflight(transform)
    return {
        "ok": result.ok,
        "errors": list(result.errors),
        "warnings": list(result.warnings),
    }


# ── Stack-run lifecycle ───────────────────────────────────────────


@router.post("/preproc/stack/run")
async def launch_stack_run(request: Request, body: StackRunBody):
    """Launch a detached PreprocStack run."""
    mgr = request.app.state.stack_manager

    try:
        stack = PreprocStack.from_dict(body.stack)
    except Exception as e:
        raise HTTPException(400, detail=f"Invalid stack: {e}")

    run_config = {
        "subject": body.subject,
        "output_dir": body.output_dir,
        "bids_dir": body.bids_dir,
        "derivatives_dir": body.derivatives_dir,
        "dataset": body.dataset,
        "sessions": list(body.sessions),
        "task": body.task,
    }

    try:
        run_id = mgr.start_run(stack, run_config, use_cache=body.use_cache)
    except ValueError as e:
        raise HTTPException(400, detail=str(e))

    return {"run_id": run_id, "status": "running"}


@router.get("/preproc/stack/runs")
async def list_stack_runs(request: Request):
    mgr = request.app.state.stack_manager
    return {"runs": mgr.list_runs()}


@router.get("/preproc/stack/{run_id}/status")
async def get_stack_status(request: Request, run_id: str):
    mgr = request.app.state.stack_manager
    summary = mgr.get_run(run_id)
    if summary is None:
        raise HTTPException(404, detail=f"Unknown run_id: {run_id}")
    return summary


@router.post("/preproc/stack/{run_id}/cancel")
async def cancel_stack_run(request: Request, run_id: str):
    """SIGTERM a running stack run; SIGKILL after the manager's grace period."""
    mgr = request.app.state.stack_manager
    result = mgr.cancel_run(run_id)
    if not result["cancelled"]:
        # 404 when the run isn't known, 409 for state mismatches.
        if result.get("reason") == "unknown run_id":
            raise HTTPException(404, detail=f"Unknown run_id: {run_id}")
        raise HTTPException(409, detail=result["reason"])
    return result


@router.get("/preproc/stack/{run_id}/manifest")
async def get_stack_manifest(request: Request, run_id: str):
    mgr = request.app.state.stack_manager
    path = mgr.get_manifest_path(run_id)
    if path is None:
        # Distinguish "no such run" from "run not done yet".
        summary = mgr.get_run(run_id)
        if summary is None:
            raise HTTPException(404, detail=f"Unknown run_id: {run_id}")
        raise HTTPException(
            409,
            detail=f"Run {run_id} has no manifest yet (status: {summary['status']})",
        )
    return json.loads(path.read_text())


# ── Helpers ───────────────────────────────────────────────────────


def _info_to_dict(info) -> dict:
    """Serialise a ``WorkflowInfo`` or ``TransformInfo`` for JSON.

    Both dataclasses share the relevant fields; we use ``getattr``
    so this works for either without import-time coupling.
    """
    base = {
        "name": info.name,
        "version": info.version,
        "description": info.description,
        "source": info.source,
        "container_bound": info.container_bound,
        "required_python": list(info.required_python),
        "required_tools": list(info.required_tools),
        "required_env": list(info.required_env),
    }
    # TransformInfo extras
    if hasattr(info, "inputs"):
        base["inputs"] = list(info.inputs)
    if hasattr(info, "outputs"):
        base["outputs"] = list(info.outputs)
    return base
