"""API routes for autoflatten — cortical surface flattening."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

router = APIRouter(tags=["autoflatten"])


# ── Request models ───────────────────────────────────────────────────────

class RunBody(BaseModel):
    subjects_dir: str
    subject: str
    hemispheres: str = "both"
    backend: str = "pyflatten"
    parallel: bool = True
    overwrite: bool = False
    template_file: str | None = None
    output_dir: str | None = None
    import_to_pycortex: bool = True
    pycortex_surface_name: str | None = None
    flat_patch_lh: str | None = None
    flat_patch_rh: str | None = None


class StatusBody(BaseModel):
    subjects_dir: str
    subject: str


# ── Endpoints ────────────────────────────────────────────────────────────

@router.get("/autoflatten/doctor")
async def doctor():
    """Check tool availability."""
    from fmriflow.preproc.autoflatten import (
        check_autoflatten_available,
        check_pycortex_available,
    )
    import shutil

    af_ok, af_detail = check_autoflatten_available()
    cx_ok, cx_detail = check_pycortex_available()
    fs_ok = shutil.which("mri_label2label") is not None

    return {
        "tools": [
            {"name": "autoflatten", "available": af_ok, "detail": af_detail},
            {"name": "pycortex", "available": cx_ok, "detail": cx_detail},
            {
                "name": "freesurfer",
                "available": fs_ok,
                "detail": "mri_label2label found" if fs_ok else "not found",
            },
        ]
    }


@router.post("/autoflatten/status")
async def status(body: StatusBody):
    """Check what exists for a subject."""
    from fmriflow.preproc.autoflatten import (
        check_surfaces,
        detect_existing_flats,
        check_pycortex_available,
    )
    from pathlib import Path

    subject_dir = Path(body.subjects_dir) / body.subject
    exists = subject_dir.is_dir()

    surfaces = check_surfaces(body.subjects_dir, body.subject) if exists else {}
    flats = detect_existing_flats(body.subjects_dir, body.subject) if exists else {}

    # Check pycortex
    pycortex_surface = None
    cx_ok, _ = check_pycortex_available()
    if cx_ok:
        try:
            import cortex
            existing = cortex.db.get_list()
            candidates = [
                f"{body.subject}fs", body.subject,
                body.subject.replace("sub-", ""),
                f"{body.subject.replace('sub-', '')}fs",
            ]
            found = [c for c in candidates if c in existing]
            if found:
                pycortex_surface = found[0]
        except Exception:
            pass

    required = ["lh.inflated", "rh.inflated"]
    has_surfaces = all(surfaces.get(s, False) for s in required)

    return {
        "subject": body.subject,
        "subject_dir_exists": exists,
        "has_surfaces": has_surfaces,
        "surfaces": surfaces,
        "flat_patches": {h: str(p) for h, p in flats.items()},
        "has_flat_patches": len(flats) == 2,
        "pycortex_surface": pycortex_surface,
    }


@router.post("/autoflatten/run")
async def start_autoflatten(request: Request, body: RunBody):
    """Start an autoflatten run in the background. Returns a run_id.

    Subscribe to ``/ws/autoflatten/{run_id}`` for live log streaming.
    Poll ``/autoflatten/runs/{run_id}`` for status + final result.
    """
    mgr = request.app.state.autoflatten_manager
    try:
        run_id = mgr.start_run(body.model_dump(exclude_none=True))
        return {"run_id": run_id, "status": "started"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/autoflatten/runs/{run_id}")
async def get_autoflatten_run(request: Request, run_id: str):
    """Get status and (if complete) result for an autoflatten run."""
    mgr = request.app.state.autoflatten_manager
    handle = mgr.active_runs.get(run_id)
    if handle is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    return {
        "run_id": handle.run_id,
        "subject": handle.subject,
        "status": handle.status,
        "result": handle.result,
        "error": handle.error,
        "started_at": handle.started_at,
        "finished_at": handle.finished_at,
        "events": handle.events,
    }


@router.get("/autoflatten/image")
async def get_autoflatten_image(path: str):
    """Serve an autoflatten-generated PNG (flatmap visualization).

    Only PNG files are served. Paths are resolved and checked for existence.
    """
    if not path:
        raise HTTPException(status_code=400, detail="path query parameter required")

    resolved = Path(path).expanduser().resolve()

    if not resolved.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")

    if resolved.suffix.lower() not in (".png", ".jpg", ".jpeg"):
        raise HTTPException(
            status_code=400,
            detail=f"Only PNG/JPEG images are served, got: {resolved.suffix}",
        )

    return FileResponse(
        str(resolved),
        media_type="image/png" if resolved.suffix.lower() == ".png" else "image/jpeg",
    )


@router.get("/autoflatten/visualizations")
async def list_autoflatten_visualizations(
    subjects_dir: str, subject: str,
):
    """List flatmap PNG files for a subject's surf/ directory.

    Useful after autoflatten has been run, or when pre-existing visualizations
    are already on disk.
    """
    surf_dir = Path(subjects_dir).expanduser().resolve() / subject / "surf"
    if not surf_dir.is_dir():
        return {"images": {}}

    images: dict[str, str] = {}
    for hemi in ("lh", "rh"):
        for pattern in (
            f"{hemi}.autoflatten.flat.patch.png",
            f"{hemi}.full.flat.patch.png",
            f"{hemi}.flat.patch.png",
        ):
            candidate = surf_dir / pattern
            if candidate.is_file():
                images[hemi] = str(candidate)
                break
    return {"images": images}
