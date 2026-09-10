"""Structural-preprocessing QC review endpoints.

Endpoints:
  GET  /preproc/subjects/{subject}/structural-qc
  POST /preproc/subjects/{subject}/structural-qc
  GET  /preproc/subjects/{subject}/structural-qc/freeview-command
  POST /preproc/subjects/{subject}/structural-qc/drawing
  GET  /preproc/subjects/{subject}/structural-qc/report
  GET  /preproc/subjects/{subject}/structural-qc/fs-file?rel=<path>
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from fmriflow.qc.structural_review import StructuralQCReview, QC_STATUSES
from fmriflow.server.services.qc_files import (
    FS_ALLOWED_SUFFIXES,
    OUT_ALLOWED_SUFFIXES,
    build_freeview_command,
    find_fs_subject_dir,
    save_drawing,
    serve_file,
)

router = APIRouter(tags=["structural-qc"])
logger = logging.getLogger(__name__)


class ReviewBody(BaseModel):
    status: str
    reviewer: str = ""
    notes: str = ""
    freeview_command_used: str | None = None


# ── helpers ─────────────────────────────────────────────────────────────


def _manifest_for(request: Request, subject: str) -> dict[str, Any]:
    mgr = request.app.state.preproc_outputs
    m = mgr.get_manifest(subject)
    if m is None:
        raise HTTPException(404, f"No manifest for subject '{subject}'")
    return m


def _fs_subject_dir(manifest: dict[str, Any]) -> Path | None:
    return find_fs_subject_dir(manifest.get("freesurfer_subjects_dir"), manifest["subject"], manifest.get("output_dir"))


def _dataset_for(request: Request, subject: str, dataset: str | None) -> str:
    """The dataset a review is filed under: the subject's manifest when the
    outputs scanner knows one, else the caller's ``?dataset=`` (a run-scoped
    view whose derivatives sit outside the scanned roots)."""
    m = request.app.state.preproc_outputs.get_manifest(subject)
    if m is not None:
        return str(m["dataset"])
    if dataset:
        return dataset
    raise HTTPException(404, f"No manifest for subject '{subject}'")


# ── review CRUD ─────────────────────────────────────────────────────────


@router.get("/structural-qc/reviews")
async def list_reviews(request: Request, dataset: str | None = None):
    """List all structural-QC reviews across datasets, or filter by one.

    Returns ``[{...review fields...}]`` newest-first (by timestamp).
    """
    store = request.app.state.structural_qc_store
    if dataset:
        reviews = store.list_for_dataset(dataset)
    else:
        reviews = store.list_all()
    rows = [r.to_dict() for r in reviews]
    rows.sort(key=lambda r: r.get("timestamp") or "", reverse=True)
    return rows


@router.get("/preproc/subjects/{subject}/structural-qc")
async def get_review(request: Request, subject: str, dataset: str | None = Query(None)):
    ds = _dataset_for(request, subject, dataset)
    store = request.app.state.structural_qc_store
    review = store.get(ds, subject)
    if review is None:
        # Default "pending" record (not persisted)
        review = StructuralQCReview(dataset=ds, subject=subject, status="pending")
    return review.to_dict()


@router.post("/preproc/subjects/{subject}/structural-qc")
async def save_review(request: Request, subject: str, body: ReviewBody, dataset: str | None = Query(None)):
    if body.status not in QC_STATUSES:
        raise HTTPException(400, f"status must be one of {QC_STATUSES}")
    ds = _dataset_for(request, subject, dataset)
    review = StructuralQCReview(
        dataset=ds,
        subject=subject,
        status=body.status,
        reviewer=body.reviewer,
        notes=body.notes,
        freeview_command_used=body.freeview_command_used,
    )
    store = request.app.state.structural_qc_store
    path = store.save(review)
    return {"saved": True, "path": str(path), "review": review.to_dict()}


# ── freeview command ────────────────────────────────────────────────────


@router.get("/preproc/subjects/{subject}/structural-qc/freeview-command")
async def freeview_command(request: Request, subject: str):
    manifest = _manifest_for(request, subject)
    fs_dir = _fs_subject_dir(manifest)
    if fs_dir is None:
        raise HTTPException(
            404,
            "Could not locate a FreeSurfer subject directory for this manifest.",
        )
    return {"command": build_freeview_command(fs_dir), "fs_subject_dir": str(fs_dir)}


@router.post("/preproc/subjects/{subject}/structural-qc/drawing")
async def upload_drawing(
    request: Request,
    subject: str,
    file: UploadFile = File(...),
    ras_x: float = Query(0.0),
    ras_y: float = Query(0.0),
    ras_z: float = Query(0.0),
):
    """Save a drawing NIfTI into the FS subject's mri/ dir and return
    a freeview command centered on the annotation centroid."""
    manifest = _manifest_for(request, subject)
    fs_dir = _fs_subject_dir(manifest)
    if fs_dir is None:
        raise HTTPException(404, "No FreeSurfer subject directory")
    return save_drawing(fs_dir, await file.read(), (ras_x, ras_y, ras_z))


# ── file serving (fmriprep report + FS files for niivue) ────────────────


@router.get("/preproc/subjects/{subject}/structural-qc/report")
async def get_report(request: Request, subject: str):
    manifest = _manifest_for(request, subject)
    out = Path(manifest.get("output_dir", ""))
    if not out.is_dir():
        raise HTTPException(404, "Manifest output_dir does not exist")
    # fmriprep writes <subject>.html at the root of output_dir
    candidates = sorted(out.glob(f"sub-{subject}*.html"))
    if not candidates:
        candidates = sorted(out.glob(f"{subject}*.html"))
    if not candidates:
        raise HTTPException(404, "No fmriprep HTML report found")
    return FileResponse(candidates[0], media_type="text/html")


@router.get("/preproc/subjects/{subject}/structural-qc/fs-file")
async def get_fs_file(request: Request, subject: str, rel: str):
    manifest = _manifest_for(request, subject)
    fs_dir = _fs_subject_dir(manifest)
    if fs_dir is None:
        raise HTTPException(404, "No FreeSurfer subject directory")

    return serve_file(fs_dir, rel, FS_ALLOWED_SUFFIXES, media_types={})


# Declared LAST on purpose: this catch-all serves the fmriprep report's
# relative asset URLs (e.g. `sub-01/figures/foo.svg`). FastAPI matches
# routes in declaration order, so the dedicated `/report`,
# `/freeview-command`, and `/fs-file` endpoints above win first.
@router.get("/preproc/subjects/{subject}/structural-qc/{rest:path}")
async def get_report_asset(request: Request, subject: str, rest: str):
    """Serve any file under the manifest's ``output_dir`` so the report
    HTML's relative figure URLs resolve.

    The report iframe sits at
    ``/api/preproc/subjects/{subject}/structural-qc/report`` so the
    browser resolves ``sub-01/figures/foo.svg`` against
    ``/api/preproc/subjects/01/structural-qc/sub-01/figures/foo.svg`` —
    that path lands here. Suffix-whitelisted, with a safe-join check
    against ``output_dir``.
    """
    manifest = _manifest_for(request, subject)
    out = Path(manifest.get("output_dir", ""))
    if not out.is_dir():
        raise HTTPException(404, "Manifest output_dir does not exist")

    return serve_file(out, rest, OUT_ALLOWED_SUFFIXES)
