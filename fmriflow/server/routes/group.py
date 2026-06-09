"""Group-run management endpoints.

Lists and surfaces ``group_summary.json`` files written by
:class:`fmriflow.group_orchestrator.GroupOrchestrator`. Read-only —
launching a group run from the UI is a follow-up.

Discovery is two-source — see
:func:`fmriflow.server.services.run_manager.discover_group_run_dirs`.
The default layout under ``$FMRIFLOW_HOME/group_runs/`` (legacy and
symlinked) is still scanned, but the run registry also contributes
runs whose ``output_dir`` is anywhere on disk. URLs stay
``/group-runs/{name}/{run_id}`` regardless of where the run actually
lives.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from fmriflow.server.services.run_manager import (
    discover_group_run_dirs, resolve_group_run_dir,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["group-runs"])


@router.get("/group-runs")
async def list_group_runs(request: Request, name: str | None = None):
    """List every group run discoverable via either the default root or
    the run registry.

    Each ``<group_name>`` directory may contain multiple timestamped
    ``<run_id>/`` subdirectories — each becomes its own row in the
    response. A legacy ``group_summary.json`` directly inside the group
    directory (pre-run-id layout) is also listed, with ``run_id = ""``.

    ``?name=<group_name>`` restricts the listing to one group's
    invocations (used by the Dashboard's RunHistory panel).
    """
    registry = request.app.state.run_manager.registry
    out: list[dict] = []
    for group_name, run_id, run_dir in discover_group_run_dirs(
        registry, name=name,
    ):
        summary_path = (run_dir / "group_summary.json")
        data = _load_json_safe(summary_path)
        if data is None:
            continue
        out.append(_summarize(
            run_dir,
            run_id=run_id or data.get("run_id", ""),
            data=data,
        ))
    out.sort(key=lambda r: r.get("started_at", ""), reverse=True)
    return out


@router.get("/group-runs/{name}/{run_id}")
async def get_group_run_by_run_id(request: Request, name: str, run_id: str):
    """Return the full ``GroupRunSummary`` for one timestamped run."""
    _check_path_segment(name, "group name")
    _check_path_segment(run_id, "run_id")
    run_dir = resolve_group_run_dir(request.app.state.run_manager.registry, name, run_id)
    if run_dir is None:
        raise HTTPException(
            status_code=404,
            detail=f"group run not found: {name}/{run_id}",
        )
    return _read_detail(run_dir)


@router.get("/group-runs/{name}/{run_id}/file/{file_path:path}")
async def get_group_run_file(
    request: Request, name: str, run_id: str, file_path: str,
):
    """Serve a single file from inside a timestamped group run directory.

    The frontend uses this to pull flatmaps, logs, and the HTML report
    over HTTP (browsers refuse ``file://`` from an http origin). The
    handler resolves the requested path under the run dir and rejects
    anything that resolves outside it.
    """
    _check_path_segment(name, "group name")
    _check_path_segment(run_id, "run_id")
    run_dir = resolve_group_run_dir(request.app.state.run_manager.registry, name, run_id)
    if run_dir is None:
        raise HTTPException(
            status_code=404,
            detail=f"group run not found: {name}/{run_id}",
        )
    return _serve_file(run_dir, file_path)


@router.get("/group-runs/{name}/file/{file_path:path}")
async def get_group_run_legacy_file(
    request: Request, name: str, file_path: str,
):
    """File-serving for the legacy (no-run_id) layout."""
    _check_path_segment(name, "group name")
    run_dir = resolve_group_run_dir(request.app.state.run_manager.registry, name, "")
    if run_dir is None:
        raise HTTPException(
            status_code=404,
            detail=f"legacy group run not found: {name}",
        )
    return _serve_file(run_dir, file_path)


@router.get("/group-runs/{name}")
async def get_group_run_legacy(request: Request, name: str):
    """Legacy: ``<group_name>/group_summary.json`` directly (no run_id)."""
    _check_path_segment(name, "group name")
    run_dir = resolve_group_run_dir(request.app.state.run_manager.registry, name, "")
    if run_dir is None:
        raise HTTPException(
            status_code=404,
            detail=f"legacy group run not found: {name}",
        )
    return _read_detail(run_dir)


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
    summary_file = run_dir / "group_summary.json"
    if not summary_file.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"group_summary.json not found in {run_dir}",
        )
    data = _load_json_safe(summary_file)
    if data is None:
        raise HTTPException(
            status_code=500,
            detail=f"could not parse {summary_file}")

    data["run_dir"] = str(run_dir)
    if (run_dir / "group_summary.html").is_file():
        data["html_report"] = "group_summary.html"
    if (run_dir / "group.log").is_file():
        data["group_log"] = "group.log"
    data["artifacts"] = _walk_artifacts(run_dir)
    return data


def _walk_artifacts(run_dir: Path) -> dict:
    """List image/text artifacts in the run dir, grouped for the UI.

    Returns a dict with two keys:
      ``group``  — list of files in the top-level run dir
      ``subjects`` — {subject_name: [file_rel_paths]} for each subject dir

    Each entry is a path RELATIVE to ``run_dir`` so the frontend can
    build URLs against ``/api/group-runs/{name}/{run_id}/file/{path}``.
    Only files with image / text / data extensions are listed; large
    .hdf5 / .npy arrays are included as download links.
    """
    SHOWABLE_EXT = {".png", ".jpg", ".jpeg", ".svg", ".html",
                    ".json", ".log", ".txt", ".npy"}
    out: dict = {"group": [], "subjects": {}}
    try:
        for entry in sorted(run_dir.iterdir()):
            if entry.is_file() and entry.suffix.lower() in SHOWABLE_EXT:
                out["group"].append(entry.name)
        gart = run_dir / "group_artifacts"
        if gart.is_dir():
            for entry in sorted(gart.iterdir()):
                if entry.is_file() and entry.suffix.lower() in SHOWABLE_EXT:
                    out["group"].append(f"group_artifacts/{entry.name}")
        subjects_dir = run_dir / "subjects"
        if subjects_dir.is_dir():
            for sub in sorted(subjects_dir.iterdir()):
                if not sub.is_dir():
                    continue
                files = []
                for entry in sorted(sub.iterdir()):
                    if entry.is_file() and entry.suffix.lower() in SHOWABLE_EXT:
                        files.append(f"subjects/{sub.name}/{entry.name}")
                if files:
                    out["subjects"][sub.name] = files
    except Exception:
        logger.warning("Failed to walk artifacts in %s", run_dir, exc_info=True)
    return out


def _serve_file(base: Path, file_path: str) -> FileResponse:
    if not file_path or file_path.startswith("/"):
        raise HTTPException(status_code=400, detail="invalid file path")
    parts = file_path.split("/")
    if any(p in ("", "..") or p.startswith(".") for p in parts):
        raise HTTPException(status_code=400, detail="invalid file path")
    # Resolve fully and ensure we're still under base.
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
    """Project a ``GroupRunSummary`` JSON down to a row for the list view."""
    subject_summaries = data.get("subject_summaries", []) or []
    status_counts = {"ok": 0, "warning": 0, "failed": 0, "unknown": 0}
    for s in subject_summaries:
        statuses = {st.get("status") for st in s.get("stages", [])}
        if "failed" in statuses:
            key = "failed"
        elif "warning" in statuses:
            key = "warning"
        elif statuses:
            key = "ok"
        else:
            key = "unknown"
        status_counts[key] = status_counts.get(key, 0) + 1
    # Group-scope stages (``group_collect``, ``group_analyze`` …) can
    # fail even when every subject succeeded; reflect that at the row
    # level so the list doesn't show such a row as all-green.
    group_stages = data.get("group_stages", []) or []
    group_failed = any(s.get("status") == "failed" for s in group_stages)
    overall_status = "failed" if (status_counts.get("failed", 0) or group_failed) else (
        "warning" if status_counts.get("warning", 0) else "ok"
    )
    return {
        "group_name": data.get("group_name", run_dir.name),
        "run_id": run_id,
        "run_dir": str(run_dir),
        "subjects": data.get("subjects", []),
        "n_subjects": len(data.get("subjects", [])),
        "status_counts": status_counts,
        "status": overall_status,
        "started_at": data.get("started_at", ""),
        "finished_at": data.get("finished_at", ""),
        "total_elapsed_s": data.get("total_elapsed_s", 0.0),
        "has_html_report": (run_dir / "group_summary.html").is_file(),
        "has_log": (run_dir / "group.log").is_file(),
    }
