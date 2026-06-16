"""API routes for fMRI preprocessing — manifest browsing + run inspection.

The legacy single-backend launch surface (``POST /preproc/run``,
``POST /preproc/configs/{f}/run``, the YAML config browse +
``POST /preproc/validate-config``) was retired in Stage 7d-A. All
new launches go through the preproc-stack routes in ``routes/stack.py``
(``POST /api/preproc/stack/run`` and friends).

What remains here is the read side:

- ``GET /preproc/backends`` — backend availability check (informational).
- ``GET /preproc/manifests`` and friends — browse / rescan / validate
  ``PreprocManifest`` files on disk. Used by the stack UI and other
  views to discover existing fmriprep outputs.
- ``POST /preproc/collect`` — build a manifest from existing
  preprocessed outputs (still standalone-useful; orthogonal to the
  legacy launch path).
- ``GET /preproc/runs[*]`` + cancel + delete — browse / manage runs
  already on disk. Stays so in-progress fmriprep jobs from the
  legacy launch surface can finish gracefully even after this
  cleanup.
"""

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


class ValidateBody(BaseModel):
    config_filename: str | None = None


# ── Endpoints ────────────────────────────────────────────────────────────

@router.get("/preproc/backends")
async def list_backends(request: Request):
    """List preprocessing backends and their availability."""
    mgr = request.app.state.preproc_manager
    return {"backends": mgr.check_backends()}


@router.get("/preproc/label-map")
async def get_label_map(version: str = "25"):
    """Return the node-friendly-name map for a given fMRIPrep major version."""
    from fmriflow.builtin.label_maps import load_label_map, available_versions
    m = load_label_map(version)
    if not m:
        raise HTTPException(404, f"No label map for version '{version}'. Available: {available_versions()}")
    return {"version": version, "labels": m}


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
    """Collect existing preprocessing outputs into a manifest.

    Standalone helper that scans a directory of finished
    preprocessed outputs and emits a manifest. Distinct from the
    deleted launch surface — this only reads, never spawns work.
    """
    mgr = request.app.state.preproc_manager
    try:
        result = mgr.collect(body.model_dump(exclude_none=True))
        return result
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

    from fmriflow.preproc.nipype_log import (
        parse_nipype_events_file,
        reconcile_with_run_state,
    )

    jsonl_path = result.get("nipype_jsonl_path")
    if jsonl_path:
        block = parse_nipype_events_file(jsonl_path, cap=cap)
        # Run-end sweep: when the parent preproc run is `done`, mark
        # any still-`running` nodes as `completed_assumed`. fmriprep
        # occasionally drops terminal log lines we'd otherwise match;
        # this is the safety net.
        block = reconcile_with_run_state(
            block, run_status=result.get("status", ""),
        )
        result["nipype_status"] = block.to_dict()
    else:
        result["nipype_status"] = {
            "counts": {"running": 0, "ok": 0, "failed": 0,
                       "completed_assumed": 0, "total_seen": 0},
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
