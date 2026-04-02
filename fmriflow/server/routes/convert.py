"""API routes for DICOM-to-BIDS conversion management."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(tags=["convert"])


# ── Request models ───────────────────────────────────────────────────────

class CollectBody(BaseModel):
    bids_dir: str
    subject: str
    source_dir: str | None = None
    heuristic: str | None = None
    sessions: list[str] | None = None
    dataset_name: str | None = None


class RunBody(BaseModel):
    source_dir: str
    bids_dir: str
    subject: str
    heuristic: str
    sessions: list[str] | None = None
    dataset_name: str | None = None
    grouping: str | None = None
    minmeta: bool = False
    overwrite: bool = True
    validate_bids: bool = True


class ScanBody(BaseModel):
    source_dir: str


class RegisterHeuristicBody(BaseModel):
    path: str
    name: str | None = None
    scanner_pattern: str | None = None
    description: str | None = None


class BatchJobBody(BaseModel):
    subject: str
    source_dir: str
    session: str = ""
    dataset_name: str | None = None
    grouping: str | None = None
    minmeta: bool | None = None
    overwrite: bool | None = None
    validate_bids: bool | None = None


class BatchRunBody(BaseModel):
    heuristic: str
    bids_dir: str
    jobs: list[BatchJobBody]
    source_root: str = ""
    max_workers: int = 2
    dataset_name: str = ""
    grouping: str = ""
    minmeta: bool = False
    overwrite: bool = True
    validate_bids: bool = True


class BatchParseYamlBody(BaseModel):
    yaml_text: str


class SaveConfigBody(BaseModel):
    name: str
    config: dict
    description: str = ""


class SaveRunConfigBody(BaseModel):
    name: str = ""
    description: str = ""
    params: dict


class SaveBatchConfigBody(BaseModel):
    name: str = ""
    description: str = ""
    params: dict


# ── Endpoints ────────────────────────────────────────────────────────────

@router.get("/convert/heuristics")
async def list_heuristics(request: Request):
    """List registered heuristics with metadata."""
    mgr = request.app.state.convert_manager
    return {"heuristics": mgr.list_heuristics()}


@router.get("/convert/tools")
async def check_tools(request: Request):
    """Check availability of conversion tools."""
    mgr = request.app.state.convert_manager
    return {"tools": mgr.check_tools()}


@router.get("/convert/manifests")
async def list_manifests(request: Request):
    """List discovered convert manifests."""
    mgr = request.app.state.convert_manager
    return {"manifests": mgr.scan_manifests()}


@router.get("/convert/manifests/{subject}")
async def get_manifest(request: Request, subject: str):
    """Get full manifest details for a subject."""
    mgr = request.app.state.convert_manager
    result = mgr.get_manifest(subject)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No manifest for subject '{subject}'")
    return result


@router.post("/convert/manifests/{subject}/validate")
async def validate_manifest(request: Request, subject: str):
    """Validate a convert manifest for a subject."""
    mgr = request.app.state.convert_manager
    return mgr.validate_manifest(subject)


@router.post("/convert/manifests/rescan")
async def rescan_manifests(request: Request):
    """Force rescan for convert manifests."""
    mgr = request.app.state.convert_manager
    mgr.invalidate_cache()
    return {"manifests": mgr.scan_manifests()}


@router.post("/convert/collect")
async def collect_bids(request: Request, body: CollectBody):
    """Build a manifest from an existing BIDS dataset."""
    mgr = request.app.state.convert_manager
    try:
        result = mgr.collect(body.model_dump(exclude_none=True))
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/convert/run")
async def start_run(request: Request, body: RunBody):
    """Start a heudiconv DICOM-to-BIDS conversion."""
    mgr = request.app.state.convert_manager
    try:
        run_id = mgr.start_run(body.model_dump(exclude_none=True))
        return {"run_id": run_id, "status": "started"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/convert/scan")
async def scan_dicom(request: Request, body: ScanBody):
    """Scan a DICOM directory for scanner info and series listing."""
    mgr = request.app.state.convert_manager
    try:
        result = mgr.scan_dicom(body.source_dir)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/convert/heuristics/register")
async def register_heuristic(request: Request, body: RegisterHeuristicBody):
    """Register a new heuristic file in the registry."""
    from fmriflow.convert.heuristics import register_heuristic as _register

    try:
        info = _register(
            path=body.path,
            name=body.name,
            scanner_pattern=body.scanner_pattern,
            description=body.description,
        )
        return {
            "name": info.name,
            "path": str(info.path),
            "description": info.description,
            "scanner_pattern": info.scanner_pattern,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Batch conversion ──────────────────────────────────────────────────────

@router.post("/convert/batch/run")
async def start_batch(request: Request, body: BatchRunBody):
    """Start a batch DICOM-to-BIDS conversion."""
    from fmriflow.convert.batch import BatchConfig, BatchJobConfig

    mgr = request.app.state.convert_manager
    try:
        batch_config = BatchConfig(
            heuristic=body.heuristic,
            bids_dir=body.bids_dir,
            jobs=[
                BatchJobConfig(
                    subject=j.subject,
                    source_dir=j.source_dir,
                    session=j.session,
                    dataset_name=j.dataset_name,
                    grouping=j.grouping,
                    minmeta=j.minmeta,
                    overwrite=j.overwrite,
                    validate_bids=j.validate_bids,
                )
                for j in body.jobs
            ],
            source_root=body.source_root,
            max_workers=body.max_workers,
            dataset_name=body.dataset_name,
            grouping=body.grouping,
            minmeta=body.minmeta,
            overwrite=body.overwrite,
            validate_bids=body.validate_bids,
        )
        batch_id = mgr.start_batch(batch_config)
        return {"batch_id": batch_id, "status": "started", "n_jobs": len(body.jobs)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/convert/batch/{batch_id}")
async def get_batch_status(request: Request, batch_id: str):
    """Get status summary for a batch conversion."""
    mgr = request.app.state.convert_manager
    result = mgr.get_batch_status(batch_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Batch '{batch_id}' not found")
    return result


@router.post("/convert/batch/{batch_id}/retry-failed")
async def retry_failed_batch(request: Request, batch_id: str):
    """Get the failed jobs from a batch for retry."""
    mgr = request.app.state.convert_manager
    try:
        result = mgr.retry_failed(batch_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/convert/batch/parse-yaml")
async def parse_batch_yaml(request: Request, body: BatchParseYamlBody):
    """Parse a YAML batch config and return as JSON."""
    from fmriflow.convert.batch import parse_batch_yaml as _parse

    try:
        config = _parse(body.yaml_text)
        return {
            "heuristic": config.heuristic,
            "bids_dir": config.bids_dir,
            "source_root": config.source_root,
            "max_workers": config.max_workers,
            "dataset_name": config.dataset_name,
            "grouping": config.grouping,
            "minmeta": config.minmeta,
            "overwrite": config.overwrite,
            "validate_bids": config.validate_bids,
            "jobs": [
                {
                    "subject": j.subject,
                    "source_dir": j.source_dir,
                    "session": j.session,
                }
                for j in config.jobs
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Saved configs ─────────────────────────────────────────────────────────

@router.get("/convert/configs")
async def list_saved_configs(request: Request):
    """List saved conversion configs."""
    store = request.app.state.convert_config_store
    return {"configs": store.list_configs()}


@router.get("/convert/configs/{filename}")
async def get_saved_config(request: Request, filename: str):
    """Get a saved conversion config."""
    store = request.app.state.convert_config_store
    result = store.get_config(filename)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Config '{filename}' not found")
    return result


@router.post("/convert/configs/save")
async def save_config(request: Request, body: SaveConfigBody):
    """Save a conversion config (raw dict)."""
    store = request.app.state.convert_config_store
    try:
        summary = store.save_config(body.name, body.config, body.description)
        return summary
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/convert/configs/save-run")
async def save_run_config(request: Request, body: SaveRunConfigBody):
    """Save a single-run conversion config from run params."""
    store = request.app.state.convert_config_store
    try:
        summary = store.save_from_run_params(body.params, body.name, body.description)
        return summary
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/convert/configs/save-batch")
async def save_batch_config(request: Request, body: SaveBatchConfigBody):
    """Save a batch conversion config from batch params."""
    store = request.app.state.convert_config_store
    try:
        summary = store.save_from_batch_params(body.params, body.name, body.description)
        return summary
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/convert/configs/{filename}")
async def delete_saved_config(request: Request, filename: str):
    """Delete a saved conversion config."""
    store = request.app.state.convert_config_store
    if not store.delete_config(filename):
        raise HTTPException(status_code=404, detail=f"Config '{filename}' not found")
    return {"deleted": True, "filename": filename}
