"""API routes for fMRI preprocessing management."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(tags=["preproc"])


# ── Request models ───────────────────────────────────────────────────────

class CollectBody(BaseModel):
    backend: str
    output_dir: str
    subject: str
    task: str | None = None
    sessions: list[str] | None = None
    bids_dir: str | None = None
    run_map: dict[str, str] | None = None
    backend_params: dict | None = None


class RunBody(BaseModel):
    backend: str
    output_dir: str
    subject: str
    bids_dir: str | None = None
    raw_dir: str | None = None
    work_dir: str | None = None
    task: str | None = None
    sessions: list[str] | None = None
    run_map: dict[str, str] | None = None
    backend_params: dict | None = None
    confounds: dict | None = None


class ValidateBody(BaseModel):
    config_filename: str | None = None


class ValidateConfigBody(BaseModel):
    backend: str
    output_dir: str
    subject: str
    bids_dir: str | None = None
    raw_dir: str | None = None
    backend_params: dict | None = None


class RunFromConfigBody(BaseModel):
    """Overrides shallow-merged on top of the YAML's preproc section."""
    subject: str | None = None
    bids_dir: str | None = None
    output_dir: str | None = None
    work_dir: str | None = None
    sessions: list[str] | None = None
    task: str | None = None
    backend_params: dict | None = None


# ── Endpoints ────────────────────────────────────────────────────────────

@router.get("/preproc/backends")
async def list_backends(request: Request):
    """List preprocessing backends and their availability."""
    mgr = request.app.state.preproc_manager
    return {"backends": mgr.check_backends()}


@router.get("/preproc/manifests")
async def list_manifests(request: Request):
    """List discovered preprocessing manifests."""
    mgr = request.app.state.preproc_manager
    return {"manifests": mgr.scan_manifests()}


@router.get("/preproc/manifests/{subject}")
async def get_manifest(request: Request, subject: str):
    """Get full manifest details for a subject."""
    mgr = request.app.state.preproc_manager
    result = mgr.get_manifest(subject)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No manifest for subject '{subject}'")
    return result


@router.post("/preproc/manifests/{subject}/validate")
async def validate_manifest(request: Request, subject: str, body: ValidateBody | None = None):
    """Validate a manifest, optionally against an analysis config."""
    mgr = request.app.state.preproc_manager
    config_filename = body.config_filename if body else None
    return mgr.validate_manifest(subject, config_filename)


@router.post("/preproc/manifests/rescan")
async def rescan_manifests(request: Request):
    """Force rescan of the derivatives directory."""
    mgr = request.app.state.preproc_manager
    mgr.invalidate_cache()
    return {"manifests": mgr.scan_manifests()}


@router.post("/preproc/collect")
async def collect_outputs(request: Request, body: CollectBody):
    """Collect existing preprocessing outputs into a manifest."""
    mgr = request.app.state.preproc_manager
    try:
        result = mgr.collect(body.model_dump(exclude_none=True))
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/preproc/run")
async def start_run(request: Request, body: RunBody):
    """Start a preprocessing run."""
    mgr = request.app.state.preproc_manager
    try:
        run_id = mgr.start_run(body.model_dump(exclude_none=True))
        return {"run_id": run_id, "status": "started"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/preproc/runs")
async def list_preproc_runs(request: Request, include_finished: bool = True):
    """List active (and optionally finished) preprocessing runs."""
    mgr = request.app.state.preproc_manager
    return {"runs": mgr.list_runs(include_finished=include_finished)}


@router.get("/preproc/runs/{run_id}")
async def get_preproc_run(request: Request, run_id: str):
    """Return summary + last 200 log lines for one run."""
    mgr = request.app.state.preproc_manager
    result = mgr.get_run(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return result


@router.get("/preproc/runs/{run_id}/live")
async def get_preproc_run_live(
    request: Request, run_id: str, cap: int = 200,
):
    """Live status for one preproc run, including parsed nipype-node events.

    Returns the run's summary plus a ``nipype_status`` block built by
    parsing ``nipype_events.jsonl`` next to the run's stdout log. When
    the backend isn't fmriprep (no parser) or no events have been
    written yet, ``nipype_status`` is an empty block.
    """
    mgr = request.app.state.preproc_manager
    result = mgr.get_run(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    from fmriflow.preproc.nipype_log import parse_nipype_events_file

    jsonl_path = result.get("nipype_jsonl_path")
    if jsonl_path:
        block = parse_nipype_events_file(jsonl_path, cap=cap)
        result["nipype_status"] = block.to_dict()
    else:
        result["nipype_status"] = {
            "counts": {"running": 0, "ok": 0, "failed": 0, "total_seen": 0},
            "recent_nodes": [],
        }
    return result


@router.post("/preproc/runs/{run_id}/cancel")
async def cancel_preproc_run(request: Request, run_id: str):
    """Cancel a running preprocessing job (SIGTERM then SIGKILL)."""
    mgr = request.app.state.preproc_manager
    result = mgr.cancel_run(run_id)
    if not result.get("cancelled"):
        raise HTTPException(status_code=409, detail=result.get("reason", "could not cancel"))
    return result


@router.delete("/preproc/runs/{run_id}")
async def delete_preproc_run(request: Request, run_id: str):
    """Delete a finished preproc run: registry dir + sub-<subject>/ outputs."""
    mgr = request.app.state.preproc_manager
    result = mgr.delete_run(run_id)
    if not result.get("deleted"):
        reason = result.get("reason", "could not delete")
        status = 409 if "running" in reason else 404
        raise HTTPException(status_code=status, detail=reason)
    return result


@router.get("/preproc/configs")
async def list_preproc_configs(request: Request):
    """List preprocessing YAML configs (with a top-level preproc: section)."""
    store = request.app.state.preproc_config_store
    summaries = store.list_configs()
    return [
        {
            "filename": s.filename,
            "path": s.path,
            "subject": s.subject,
            "backend": s.backend,
            "bids_dir": s.bids_dir,
            "output_dir": s.output_dir,
            "container": s.container,
            "container_type": s.container_type,
            "mode": s.mode,
        }
        for s in summaries
    ]


@router.get("/preproc/configs/{filename}")
async def get_preproc_config(request: Request, filename: str):
    """Return full parsed config + raw YAML for one preproc config file."""
    store = request.app.state.preproc_config_store
    result = store.get_config(filename)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Preproc config '{filename}' not found",
        )
    return result


@router.post("/preproc/configs/{filename}/run")
async def run_preproc_config(
    request: Request,
    filename: str,
    body: RunFromConfigBody | None = None,
):
    """Start a preprocessing run from a YAML config file's preproc: section."""
    store = request.app.state.preproc_config_store
    config_info = store.get_config(filename)
    if config_info is None:
        raise HTTPException(
            status_code=404,
            detail=f"Preproc config '{filename}' not found",
        )

    mgr = request.app.state.preproc_manager
    overrides = body.model_dump(exclude_none=True) if body else None
    try:
        run_id = mgr.start_run_from_config_file(
            config_info["path"], overrides=overrides,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"run_id": run_id, "status": "started", "config": filename}


@router.post("/preproc/validate-config")
async def validate_preproc_config(request: Request, body: ValidateConfigBody):
    """Validate a preprocessing config without running."""
    from fmriflow.preproc.backends import get_backend
    from fmriflow.preproc.manifest import PreprocConfig

    try:
        config = PreprocConfig(
            subject=body.subject,
            backend=body.backend,
            output_dir=body.output_dir,
            bids_dir=body.bids_dir,
            raw_dir=body.raw_dir,
            backend_params=body.backend_params or {},
        )
        backend = get_backend(body.backend)
        errors = backend.validate(config)
        return {"valid": len(errors) == 0, "errors": errors}
    except Exception as e:
        return {"valid": False, "errors": [str(e)]}
