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


class RunFromAutoflattenConfigBody(BaseModel):
    """Overrides shallow-merged on top of the YAML's autoflatten section."""
    subjects_dir: str | None = None
    subject: str | None = None
    hemispheres: str | None = None
    backend: str | None = None
    output_dir: str | None = None
    overwrite: bool | None = None


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


@router.get("/autoflatten/configs")
async def list_autoflatten_configs(request: Request):
    """List autoflatten YAML configs with a top-level autoflatten: section."""
    store = request.app.state.autoflatten_config_store
    summaries = store.list_configs()
    return [
        {
            "filename": s.filename,
            "path": s.path,
            "subject": s.subject,
            "subjects_dir": s.subjects_dir,
            "hemispheres": s.hemispheres,
            "backend": s.backend,
            "output_dir": s.output_dir,
        }
        for s in summaries
    ]


@router.get("/autoflatten/configs/{filename}")
async def get_autoflatten_config(request: Request, filename: str):
    """Return full parsed config + raw YAML for one autoflatten config."""
    store = request.app.state.autoflatten_config_store
    result = store.get_config(filename)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Autoflatten config '{filename}' not found",
        )
    return result


@router.post("/autoflatten/configs/{filename}/run")
async def run_autoflatten_config(
    request: Request,
    filename: str,
    body: RunFromAutoflattenConfigBody | None = None,
):
    """Start an autoflatten run from a YAML config file."""
    store = request.app.state.autoflatten_config_store
    info = store.get_config(filename)
    if info is None:
        raise HTTPException(
            status_code=404,
            detail=f"Autoflatten config '{filename}' not found",
        )
    mgr = request.app.state.autoflatten_manager
    overrides = body.model_dump(exclude_none=True) if body else None
    try:
        run_id = mgr.start_run_from_config_file(
            info["path"], overrides=overrides,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"run_id": run_id, "status": "started", "config": filename}


@router.get("/autoflatten/runs")
async def list_autoflatten_runs(request: Request, include_finished: bool = True):
    """List active (and optionally finished) autoflatten runs."""
    mgr = request.app.state.autoflatten_manager
    return {"runs": mgr.list_runs(include_finished=include_finished)}


@router.get("/autoflatten/runs/{run_id}")
async def get_autoflatten_run(request: Request, run_id: str):
    """Get status, result, events, and log tail for an autoflatten run.

    Now backed by AutoflattenManager.get_run which also resolves finished
    runs from the on-disk registry, so polling keeps working after a
    server restart. Response shape is a superset of the original:
    adds pid, is_reattached, log_path, log_tail.
    """
    mgr = request.app.state.autoflatten_manager
    result = mgr.get_run(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return result


@router.post("/autoflatten/runs/{run_id}/cancel")
async def cancel_autoflatten_run(request: Request, run_id: str):
    """Cancel a running autoflatten subprocess (SIGTERM → SIGKILL)."""
    mgr = request.app.state.autoflatten_manager
    result = mgr.cancel_run(run_id)
    if not result.get("cancelled"):
        raise HTTPException(status_code=409, detail=result.get("reason", "could not cancel"))
    return result


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
