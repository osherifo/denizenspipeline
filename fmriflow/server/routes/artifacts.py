"""Artifact serving endpoints."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

router = APIRouter(tags=["artifacts"])
logger = logging.getLogger(__name__)


# Files that must never be deleted via the API — they're metadata, not artifacts.
_PROTECTED_NAMES = {"run_summary.json", "pipeline.log"}

MEDIA_TYPES = {
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.svg': 'image/svg+xml',
    '.json': 'application/json',
    '.html': 'text/html',
    '.hdf5': 'application/octet-stream',
    '.h5': 'application/octet-stream',
    '.npz': 'application/octet-stream',
}


@router.get("/runs/{run_id}/artifacts/{artifact_name:path}")
async def get_artifact(request: Request, run_id: str, artifact_name: str):
    """Serve an artifact file from a run's output directory."""
    store = request.app.state.run_store
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    output_dir = Path(run['output_dir'])
    artifact_path = output_dir / artifact_name

    # Prevent directory traversal
    try:
        artifact_path = artifact_path.resolve()
        output_dir_resolved = output_dir.resolve()
        if not str(artifact_path).startswith(str(output_dir_resolved)):
            raise HTTPException(status_code=403, detail="Access denied")
    except (ValueError, OSError):
        raise HTTPException(status_code=400, detail="Invalid path")

    if not artifact_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Artifact '{artifact_name}' not found in run '{run_id}'",
        )

    # For JSON files, return parsed content
    if artifact_path.suffix == '.json':
        import json
        try:
            data = json.loads(artifact_path.read_text())
            return JSONResponse(data)
        except Exception:
            pass

    media_type = MEDIA_TYPES.get(artifact_path.suffix.lower(), 'application/octet-stream')
    return FileResponse(artifact_path, media_type=media_type)


@router.delete("/runs/{run_id}/artifacts/{artifact_name:path}")
async def delete_artifact(request: Request, run_id: str, artifact_name: str):
    """Delete a run artifact (file or directory) from the run's output dir."""
    store = request.app.state.run_store
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    output_dir = Path(run['output_dir']).resolve()
    artifact_path = (output_dir / artifact_name).resolve()

    # Prevent directory traversal — the resolved path must stay inside output_dir.
    if not artifact_path.is_relative_to(output_dir):
        raise HTTPException(status_code=403, detail="Access denied")

    # Don't allow deleting the output dir itself.
    if artifact_path == output_dir:
        raise HTTPException(status_code=400, detail="Refusing to delete output dir")

    # Don't allow deleting protected metadata.
    base_name = artifact_path.name
    if base_name in _PROTECTED_NAMES:
        raise HTTPException(
            status_code=400,
            detail=f"Refusing to delete protected file: {base_name}",
        )

    if not artifact_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Artifact '{artifact_name}' not found in run '{run_id}'",
        )

    try:
        if artifact_path.is_dir():
            shutil.rmtree(artifact_path)
        else:
            artifact_path.unlink()
    except OSError as e:
        logger.error("Failed to delete artifact %s: %s", artifact_path, e)
        raise HTTPException(status_code=500, detail=f"Delete failed: {e}")

    logger.info("Deleted artifact: %s", artifact_path)
    return {"deleted": True, "path": str(artifact_path)}
