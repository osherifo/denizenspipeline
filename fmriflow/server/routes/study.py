"""Study-runs HTTP API — one scope up from the group-runs routes.

Endpoints:

  GET  /api/study-runs                       list every study run
  GET  /api/study-runs?name=<study>          filter to one study's invocations
  GET  /api/study-runs/{name}/{run_id}       full StudyRunSummary + artifacts
  GET  /api/study-runs/{name}/{run_id}/file/{path}   serve a file inside the run

Mirrors :mod:`fmriflow.server.routes.group` line for line — the only
differences are the on-disk root (``study_runs/``) and the summary
filename (``study_summary.json``).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from fmriflow.server.services.run_manager import (
    discover_study_run_dirs, resolve_study_run_dir,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["study"])


# ─── routes ─────────────────────────────────────────────────────


@router.get("/study-runs")
async def list_study_runs(request: Request, name: str | None = None):
    """List every study run discoverable via either the default root or
    the run registry — same two-source pattern as ``/group-runs``.

    Each ``<study_name>/`` directory may contain multiple timestamped
    ``<run_id>/`` subdirectories — each becomes its own row.
    ``?name=<study_name>`` restricts to one study.
    """
    registry = request.app.state.run_manager.registry
    out: list[dict] = []
    for study_name, run_id, run_dir in discover_study_run_dirs(
        registry, name=name,
    ):
        summary_path = run_dir / "study_summary.json"
        data = _load_json_safe(summary_path)
        if data is None:
            continue
        out.append(_summarize(
            run_dir, run_id=run_id or data.get("run_id", ""), data=data,
        ))
    out.sort(key=lambda r: r.get("started_at", ""), reverse=True)
    return out


@router.get("/study-runs/{name}/{run_id}")
async def get_study_run(request: Request, name: str, run_id: str):
    """Return the full ``StudyRunSummary`` for one timestamped run."""
    _check_path_segment(name, "study name")
    _check_path_segment(run_id, "run_id")
    run_dir = resolve_study_run_dir(request.app.state.run_manager.registry, name, run_id)
    if run_dir is None:
        raise HTTPException(
            status_code=404,
            detail=f"study run not found: {name}/{run_id}",
        )
    return _read_detail(run_dir)


@router.get("/study-runs/{name}/{run_id}/file/{file_path:path}")
async def get_study_run_file(
    request: Request, name: str, run_id: str, file_path: str,
):
    """Serve a single file from inside a timestamped study run directory."""
    _check_path_segment(name, "study name")
    _check_path_segment(run_id, "run_id")
    run_dir = resolve_study_run_dir(request.app.state.run_manager.registry, name, run_id)
    if run_dir is None:
        raise HTTPException(
            status_code=404,
            detail=f"study run not found: {name}/{run_id}",
        )
    return _serve_file(run_dir, file_path)


# ─── helpers ───────────────────────────────────────────────────


def _check_path_segment(value: str, label: str) -> None:
    if not value or "/" in value or ".." in value or value.startswith("."):
        raise HTTPException(status_code=400, detail=f"invalid {label}: {value!r}")


def _load_json_safe(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except Exception:
        logger.warning("Could not parse %s", path, exc_info=True)
        return None


def _read_detail(run_dir: Path) -> dict:
    summary_file = run_dir / "study_summary.json"
    if not summary_file.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"study_summary.json not found in {run_dir}",
        )
    data = _load_json_safe(summary_file)
    if data is None:
        raise HTTPException(
            status_code=500, detail=f"could not parse {summary_file}")

    data["run_dir"] = str(run_dir)
    if (run_dir / "study_summary.html").is_file():
        data["html_report"] = "study_summary.html"
    if (run_dir / "study.log").is_file():
        data["study_log"] = "study.log"
    data["artifacts"] = _walk_artifacts(run_dir)
    return data


def _walk_artifacts(run_dir: Path) -> dict:
    """List image/text artifacts in the run dir, grouped for the UI.

    Returns a dict with three keys:
      ``study``    — files at the top level of the run dir
      ``groups``   — {group_label: [file_rel_paths]} for each group dir
      ``subjects`` — {group_label: {subject: [file_rel_paths]}} for the
                     per-subject plots nested under each group's run dir

    Each entry is a path RELATIVE to ``run_dir`` so the frontend can
    build URLs against ``/api/study-runs/{name}/{run_id}/file/{path}``.
    """
    SHOWABLE_EXT = {".png", ".jpg", ".jpeg", ".svg", ".html",
                    ".json", ".log", ".txt", ".npy"}
    out: dict = {"study": [], "groups": {}, "subjects": {}}
    try:
        for entry in sorted(run_dir.iterdir()):
            if entry.is_file() and entry.suffix.lower() in SHOWABLE_EXT:
                out["study"].append(entry.name)
        sart = run_dir / "study_artifacts"
        if sart.is_dir():
            for entry in sorted(sart.iterdir()):
                if entry.is_file() and entry.suffix.lower() in SHOWABLE_EXT:
                    out["study"].append(f"study_artifacts/{entry.name}")
        groups_dir = run_dir / "groups"
        if groups_dir.is_dir():
            for grp in sorted(groups_dir.iterdir()):
                if not grp.is_dir():
                    continue
                files = []
                for entry in sorted(grp.iterdir()):
                    if entry.is_file() and entry.suffix.lower() in SHOWABLE_EXT:
                        files.append(f"groups/{grp.name}/{entry.name}")
                # Each group dir contains its own <group_run_id>/ —
                # surface its top-level group summaries / HTML, plus the
                # per-subject plots nested under <group_run_id>/subjects/<subj>/.
                for inner in sorted(grp.iterdir()):
                    if not inner.is_dir() or inner.name == "latest":
                        continue
                    for entry in sorted(inner.iterdir()):
                        if entry.is_file() and entry.suffix.lower() in SHOWABLE_EXT:
                            files.append(
                                f"groups/{grp.name}/{inner.name}/{entry.name}"
                            )
                    subj_root = inner / "subjects"
                    if subj_root.is_dir():
                        for subj in sorted(subj_root.iterdir()):
                            if not subj.is_dir():
                                continue
                            sfiles = [
                                f"groups/{grp.name}/{inner.name}/subjects/{subj.name}/{e.name}"
                                for e in sorted(subj.iterdir())
                                if e.is_file() and e.suffix.lower() in SHOWABLE_EXT
                            ]
                            if sfiles:
                                out["subjects"].setdefault(grp.name, {})[subj.name] = sfiles
                if files:
                    out["groups"][grp.name] = files
    except Exception:
        logger.warning("Failed to walk artifacts in %s", run_dir, exc_info=True)
    return out


def _serve_file(base: Path, file_path: str) -> FileResponse:
    if not file_path or file_path.startswith("/"):
        raise HTTPException(status_code=400, detail="invalid file path")
    parts = file_path.split("/")
    if any(p in ("", "..") or p.startswith(".") for p in parts):
        raise HTTPException(status_code=400, detail="invalid file path")
    try:
        full = (base / file_path).resolve(strict=False)
        base_resolved = base.resolve(strict=False)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not str(full).startswith(str(base_resolved) + "/") and full != base_resolved:
        raise HTTPException(status_code=400, detail="path escapes run dir")
    if not full.is_file():
        raise HTTPException(status_code=404, detail=f"not a file: {file_path}")
    return FileResponse(str(full))


def _summarize(run_dir: Path, *, run_id: str, data: dict) -> dict:
    """Project a ``StudyRunSummary`` JSON down to a row for the list view."""
    from fmriflow.core.run_summary import derive_group_status
    groups = data.get("group_summaries", []) or []
    labels = data.get("group_labels", []) or []
    # Count of groups for the study includes those that failed before
    # producing a group_summary — labels is the authoritative N.
    n_groups_total = max(len(labels), len(groups))
    group_statuses = [derive_group_status(g) for g in groups]
    n_failed_groups = sum(1 for s in group_statuses if s == 'failed')
    n_warning_groups = sum(1 for s in group_statuses if s == 'warning')
    # Groups missing from group_summaries (failed before writing) count
    # as failed for the overall rollup.
    missing_groups = max(0, n_groups_total - len(groups))
    n_failed_groups += missing_groups
    n_ok = max(0, n_groups_total - n_failed_groups - n_warning_groups)
    status_counts = {
        "ok": n_ok,
        "warning": n_warning_groups,
        "failed": n_failed_groups,
    }
    study_stages = data.get("study_stages", []) or []
    study_failed = any(s.get("status") == "failed" for s in study_stages)
    study_warning = any(s.get("status") == "warning" for s in study_stages)
    # Trust the orchestrator-written status when present — it has the
    # full per-stage / per-plugin context. Fall back to the derived
    # rollup for older summaries that pre-date StudyRunSummary.status.
    saved_status = data.get("status")
    if saved_status in ("ok", "warning", "failed"):
        overall_status = saved_status
    elif n_failed_groups or study_failed:
        overall_status = "failed"
    elif n_warning_groups or study_warning:
        overall_status = "warning"
    else:
        overall_status = "ok"
    return {
        "study_name": data.get("study_name", run_dir.parent.name),
        "run_id": run_id,
        "run_dir": str(run_dir),
        "group_labels": labels,
        "n_groups": n_groups_total,
        "status_counts": status_counts,
        "status": overall_status,
        "started_at": data.get("started_at", ""),
        "finished_at": data.get("finished_at", ""),
        "total_elapsed_s": data.get("total_elapsed_s", 0.0),
        "has_html_report": (run_dir / "study_summary.html").is_file(),
        "has_log": (run_dir / "study.log").is_file(),
    }
