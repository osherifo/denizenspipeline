"""Structural-preprocessing QC review endpoints.

Endpoints:
  GET  /preproc/subjects/{subject}/structural-qc
  POST /preproc/subjects/{subject}/structural-qc
  GET  /preproc/subjects/{subject}/structural-qc/freeview-command
  GET  /preproc/subjects/{subject}/structural-qc/report
  GET  /preproc/subjects/{subject}/structural-qc/fs-file?rel=<path>
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from fmriflow.qc.structural_review import StructuralQCReview, QC_STATUSES

router = APIRouter(tags=["structural-qc"])
logger = logging.getLogger(__name__)


# Files we'll serve from the FS subject dir for in-browser viewing.
_FS_ALLOWED_SUFFIXES = {
    ".nii", ".gz", ".mgz",
    ".pial", ".white", ".inflated", ".smoothwm",
    ".png", ".svg",
}


class ReviewBody(BaseModel):
    status: str
    reviewer: str = ""
    notes: str = ""
    freeview_command_used: str | None = None


# ── helpers ─────────────────────────────────────────────────────────────


def _manifest_for(request: Request, subject: str) -> dict[str, Any]:
    mgr = request.app.state.preproc_manager
    m = mgr.get_manifest(subject)
    if m is None:
        raise HTTPException(404, f"No manifest for subject '{subject}'")
    return m


def _safe_join(root: Path, rel: str) -> Path:
    """Resolve `root / rel` and refuse to leave `root`."""
    target = (root / rel).resolve()
    root_resolved = root.resolve()
    if not str(target).startswith(str(root_resolved) + "/") and target != root_resolved:
        raise HTTPException(403, "Path escapes root")
    return target


def _fs_subject_dir(manifest: dict[str, Any]) -> Path | None:
    """Locate the FreeSurfer subject directory for the manifest, if any."""
    fs_dir = manifest.get("freesurfer_subjects_dir")
    subject = manifest["subject"]
    if fs_dir:
        cand = Path(fs_dir) / f"sub-{subject}"
        if cand.is_dir():
            return cand
        cand2 = Path(fs_dir) / subject
        if cand2.is_dir():
            return cand2
    # Fallback: common fmriprep layouts under output_dir
    out = Path(manifest.get("output_dir", ""))
    for base in (
        out / "sourcedata" / "freesurfer",
        out / "freesurfer",
        out.parent / "freesurfer",
    ):
        for name in (f"sub-{subject}", subject):
            cand = base / name
            if cand.is_dir():
                return cand
    return None


def _build_freeview_command(fs_subject_dir: Path) -> str:
    """Build a freeview command using the files that actually exist."""
    parts: list[str] = ["freeview"]
    mri = fs_subject_dir / "mri"
    surf = fs_subject_dir / "surf"

    volumes = [
        ("T1.mgz", ""),
        ("brainmask.mgz", ":colormap=heat:opacity=0.3"),
        ("aseg.mgz", ":colormap=lut:opacity=0.3"),
    ]
    for name, opts in volumes:
        p = mri / name
        if p.is_file():
            parts.append(f"-v {p}{opts}")

    surfaces = [
        ("lh.pial", ":edgecolor=red"),
        ("rh.pial", ":edgecolor=red"),
        ("lh.white", ":edgecolor=yellow"),
        ("rh.white", ":edgecolor=yellow"),
    ]
    for name, opts in surfaces:
        p = surf / name
        if p.is_file():
            parts.append(f"-f {p}{opts}")

    return " \\\n  ".join(parts)


# ── review CRUD ─────────────────────────────────────────────────────────


@router.get("/preproc/subjects/{subject}/structural-qc")
async def get_review(request: Request, subject: str):
    manifest = _manifest_for(request, subject)
    store = request.app.state.structural_qc_store
    review = store.get(manifest["dataset"], subject)
    if review is None:
        # Default "pending" record (not persisted)
        review = StructuralQCReview(
            dataset=manifest["dataset"], subject=subject, status="pending"
        )
    return review.to_dict()


@router.post("/preproc/subjects/{subject}/structural-qc")
async def save_review(request: Request, subject: str, body: ReviewBody):
    if body.status not in QC_STATUSES:
        raise HTTPException(400, f"status must be one of {QC_STATUSES}")
    manifest = _manifest_for(request, subject)
    review = StructuralQCReview(
        dataset=manifest["dataset"],
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
    return {"command": _build_freeview_command(fs_dir), "fs_subject_dir": str(fs_dir)}


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

    # Validate the suffix from the *requested* rel — the caller controls
    # this, and we want to allow symlinked targets like
    # `lh.pial → lh.pial.T1` whose resolved suffix wouldn't pass.
    rel_suffix = Path(rel).suffix.lower()
    if rel_suffix not in _FS_ALLOWED_SUFFIXES:
        raise HTTPException(403, f"Suffix not allowed: {rel_suffix}")

    target = _safe_join(fs_dir, rel)
    if not target.is_file():
        raise HTTPException(404, f"File not found: {rel}")
    return FileResponse(target, media_type="application/octet-stream")
