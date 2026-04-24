"""End-to-end workflow orchestration routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(tags=["workflows"])


# ── Config browsing ──────────────────────────────────────────────────────

@router.get("/workflows/configs")
async def list_workflow_configs(request: Request):
    """List workflow YAML configs discovered under ./experiments/workflows/."""
    store = request.app.state.workflow_config_store
    return [
        {
            "filename": s.filename,
            "path": s.path,
            "name": s.name,
            "n_stages": s.n_stages,
            "stage_names": s.stage_names,
        }
        for s in store.list_configs()
    ]


@router.get("/workflows/configs/{filename}")
async def get_workflow_config(request: Request, filename: str):
    """Return full parsed config + raw YAML for one workflow."""
    store = request.app.state.workflow_config_store
    result = store.get_config(filename)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Workflow config '{filename}' not found",
        )
    return result


@router.post("/workflows/configs/{filename}/run")
async def run_workflow_config(request: Request, filename: str):
    """Kick off an end-to-end workflow defined by a YAML file."""
    store = request.app.state.workflow_config_store
    info = store.get_config(filename)
    if info is None:
        raise HTTPException(
            status_code=404,
            detail=f"Workflow config '{filename}' not found",
        )
    mgr = request.app.state.workflow_manager
    try:
        run_id = mgr.start_workflow_from_file(info["path"])
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"run_id": run_id, "status": "started", "config": filename}


# ── Run management ──────────────────────────────────────────────────────

@router.get("/workflows/runs")
async def list_workflow_runs(request: Request, include_finished: bool = True):
    """List active + (optionally) recent workflow runs."""
    mgr = request.app.state.workflow_manager
    return {"runs": mgr.list_runs(include_finished=include_finished)}


@router.get("/workflows/runs/{run_id}")
async def get_workflow_run(request: Request, run_id: str):
    """Get a workflow run's per-stage status + child run_ids."""
    mgr = request.app.state.workflow_manager
    result = mgr.get_run(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Workflow run '{run_id}' not found")
    return result


@router.post("/workflows/runs/{run_id}/cancel")
async def cancel_workflow_run(request: Request, run_id: str):
    """Request cancellation of a running workflow.

    Sets a cancel flag the orchestrator picks up on its next poll. The
    current stage's child subprocess is then SIGTERMed via the stage
    manager's own cancel_run.
    """
    mgr = request.app.state.workflow_manager
    result = mgr.cancel_run(run_id)
    if not result.get("cancelled"):
        raise HTTPException(status_code=409, detail=result.get("reason", "could not cancel"))
    return result


@router.delete("/workflows/runs/{run_id}")
async def delete_workflow_run(request: Request, run_id: str):
    """Delete a finished workflow run. Cascades to each stage's
    child run so the same per-stage cleanup rules apply (subject BIDS
    for convert, sub-<subject>/ for preproc, per-run output subdir for
    analysis, registry only for autoflatten)."""
    mgr = request.app.state.workflow_manager
    result = mgr.delete_run(run_id)
    if not result.get("deleted"):
        reason = result.get("reason", "could not delete")
        status = 409 if "running" in reason else 404
        raise HTTPException(status_code=status, detail=reason)
    return result
