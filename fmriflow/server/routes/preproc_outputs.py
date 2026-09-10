"""Preprocessing outputs: manifests, validation, collecting existing derivatives, label maps."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(tags=["preproc-outputs"])


class CollectBody(BaseModel):
    backend: str
    output_dir: str
    subject: str
    task: str | None = None
    sessions: list[str] | None = None
    bids_dir: str | None = None
    run_map: dict[str, str] | None = None
    backend_params: dict | None = None


def _outputs(request: Request):
    return request.app.state.preproc_outputs


@router.get("/preproc/label-map")
async def get_label_map(version: str = "25"):
    """Node-friendly-name map for a given fMRIPrep major version."""
    from fmriflow.builtin.label_maps import available_versions, load_label_map
    m = load_label_map(version)
    if not m:
        raise HTTPException(404, f"No label map for version '{version}'. Available: {available_versions()}")
    return {"version": version, "labels": m}


@router.get("/preproc/manifests")
async def list_manifests(request: Request):
    return {"manifests": _outputs(request).scan_manifests()}


@router.post("/preproc/manifests/rescan")
async def rescan_manifests(request: Request):
    out = _outputs(request)
    out.invalidate_cache()
    return {"manifests": out.scan_manifests()}


@router.get("/preproc/manifests/{subject}")
async def get_manifest(request: Request, subject: str):
    result = _outputs(request).get_manifest(subject)
    if result is None:
        raise HTTPException(404, f"No manifest for subject '{subject}'")
    return result


@router.post("/preproc/manifests/{subject}/validate")
async def validate_manifest(request: Request, subject: str, config_filename: str | None = None):
    return _outputs(request).validate_manifest(subject, config_filename)


@router.post("/preproc/collect")
async def collect_outputs(request: Request, body: CollectBody):
    try:
        return _outputs(request).collect(body.model_dump(exclude_none=True))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
