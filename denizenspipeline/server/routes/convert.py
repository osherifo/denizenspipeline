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
    from denizenspipeline.convert.heuristics import register_heuristic as _register

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
