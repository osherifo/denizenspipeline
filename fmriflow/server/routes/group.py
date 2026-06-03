"""Group-run management endpoints.

Lists and surfaces ``group_summary.json`` files written by
:class:`fmriflow.group_orchestrator.GroupOrchestrator`. Read-only —
launching a group run from the UI is a follow-up.

Layout (current):
    $FMRIFLOW_HOME/group_runs/<group_name>/<run_id>/group_summary.json
    $FMRIFLOW_HOME/group_runs/<group_name>/<run_id>/group.log
    $FMRIFLOW_HOME/group_runs/<group_name>/<run_id>/subjects/<sub>/...
    $FMRIFLOW_HOME/group_runs/<group_name>/latest -> <run_id>/

Legacy (pre-run-id layout, still listed):
    $FMRIFLOW_HOME/group_runs/<group_name>/group_summary.json
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from fmriflow.core import paths

logger = logging.getLogger(__name__)

router = APIRouter(tags=["group-runs"])


@router.get("/group-runs")
async def list_group_runs(name: str | None = None):
    """List every group run found under ``$FMRIFLOW_HOME/group_runs/``.

    Each ``<group_name>`` directory may contain multiple timestamped
    ``<run_id>/`` subdirectories — each becomes its own row in the
    response. A legacy ``group_summary.json`` directly inside the group
    directory (pre-run-id layout) is also listed, with ``run_id = ""``.

    ``?name=<group_name>`` restricts the listing to one group's
    invocations (used by the Dashboard's RunHistory panel).
    """
    root = paths.group_runs_root()
    out: list[dict] = []
    for group_dir in sorted(root.iterdir() if root.exists() else []):
        if not group_dir.is_dir():
            continue
        if name is not None and group_dir.name != name:
            continue

        # Legacy layout: group_summary.json directly under <group_name>/.
        legacy = group_dir / "group_summary.json"
        if legacy.is_file():
            data = _load_json_safe(legacy)
            if data is not None:
                out.append(_summarize(group_dir, run_id="", data=data))

        # New layout: walk timestamped subdirectories.
        for run_dir in sorted(group_dir.iterdir()):
            if not run_dir.is_dir() or run_dir.name == "latest":
                continue
            summary = run_dir / "group_summary.json"
            if not summary.is_file():
                continue
            data = _load_json_safe(summary)
            if data is None:
                continue
            out.append(_summarize(run_dir,
                                  run_id=data.get("run_id") or run_dir.name,
                                  data=data))

    out.sort(key=lambda r: r.get("started_at", ""), reverse=True)
    return out


@router.get("/group-runs/{name}/{run_id}")
async def get_group_run_by_run_id(name: str, run_id: str):
    """Return the full ``GroupRunSummary`` for one timestamped run."""
    group_dir = _resolve_group_dir(name)
    _check_path_segment(run_id, "run_id")
    return _read_detail(group_dir / run_id)


@router.get("/group-runs/{name}/{run_id}/file/{file_path:path}")
async def get_group_run_file(name: str, run_id: str, file_path: str):
    """Serve a single file from inside a timestamped group run directory.

    The frontend uses this to pull flatmaps, logs, and the HTML report
    over HTTP (browsers refuse ``file://`` from an http origin). The
    handler resolves the requested path under the run dir and rejects
    anything that resolves outside it.
    """
    group_dir = _resolve_group_dir(name)
    _check_path_segment(run_id, "run_id")
    return _serve_file(group_dir / run_id, file_path)


@router.get("/group-runs/{name}/file/{file_path:path}")
async def get_group_run_legacy_file(name: str, file_path: str):
    """File-serving for the legacy (no-run_id) layout."""
    return _serve_file(_resolve_group_dir(name), file_path)


@router.get("/group-runs/{name}")
async def get_group_run_legacy(name: str):
    """Legacy: ``<group_name>/group_summary.json`` directly (no run_id)."""
    return _read_detail(_resolve_group_dir(name))


# ─── helpers ───────────────────────────────────────────────────

def _resolve_group_dir(name: str) -> Path:
    _check_path_segment(name, "group name")
    return paths.group_runs_root() / name


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
    return {
        "group_name": data.get("group_name", run_dir.name),
        "run_id": run_id,
        "run_dir": str(run_dir),
        "subjects": data.get("subjects", []),
        "n_subjects": len(data.get("subjects", [])),
        "status_counts": status_counts,
        "started_at": data.get("started_at", ""),
        "finished_at": data.get("finished_at", ""),
        "total_elapsed_s": data.get("total_elapsed_s", 0.0),
        "has_html_report": (run_dir / "group_summary.html").is_file(),
        "has_log": (run_dir / "group.log").is_file(),
    }
