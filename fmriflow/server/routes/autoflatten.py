"""API routes for autoflatten — cortical surface flattening."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
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
async def run_autoflatten(body: RunBody):
    """Run autoflatten (or import pre-computed patches)."""
    from fmriflow.preproc.autoflatten import (
        AutoflattenConfig,
        AutoflattenRecord,
        run_autoflatten as _run,
    )

    config = AutoflattenConfig(
        subjects_dir=body.subjects_dir,
        subject=body.subject,
        hemispheres=body.hemispheres,
        backend=body.backend,
        parallel=body.parallel,
        overwrite=body.overwrite,
        template_file=body.template_file,
        output_dir=body.output_dir,
        import_to_pycortex=body.import_to_pycortex,
        pycortex_surface_name=body.pycortex_surface_name,
        flat_patch_lh=body.flat_patch_lh,
        flat_patch_rh=body.flat_patch_rh,
    )

    errors = config.validate()
    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))

    try:
        result = _run(config)
        record = AutoflattenRecord.from_result(result, config)
        return {
            "result": {
                "subject": result.subject,
                "source": result.source,
                "hemispheres": result.hemispheres,
                "flat_patches": result.flat_patches,
                "visualizations": result.visualizations,
                "pycortex_surface": result.pycortex_surface,
                "elapsed_s": result.elapsed_s,
            },
            "record": record.to_dict(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
