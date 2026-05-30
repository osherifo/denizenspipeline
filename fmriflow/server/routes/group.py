"""Group-run management endpoints.

Lists and surfaces ``group_summary.json`` files written by
:class:`fmriflow.group_orchestrator.GroupOrchestrator`. Phase 4 — read-only
endpoints powering the Group Runs view; launching a group run from the UI
is a separate follow-up.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

from fmriflow.core import paths

logger = logging.getLogger(__name__)

router = APIRouter(tags=["group-runs"])


@router.get("/group-runs")
async def list_group_runs():
    """List group runs found under ``$FMRIFLOW_HOME/group_runs/``.

    Each entry is a thin summary — group name, subject count, status
    counts, total elapsed, started/finished timestamps. The detail
    endpoint returns the full ``GroupRunSummary`` body.
    """
    root = paths.group_runs_root()
    out = []
    for d in sorted(root.iterdir() if root.exists() else []):
        if not d.is_dir():
            continue
        summary_file = d / "group_summary.json"
        if not summary_file.is_file():
            continue
        try:
            data = json.loads(summary_file.read_text())
        except Exception:
            logger.warning("Could not parse %s", summary_file, exc_info=True)
            continue
        out.append(_summarize(d, data))
    out.sort(key=lambda r: r.get("started_at", ""), reverse=True)
    return out


@router.get("/group-runs/{name}")
async def get_group_run(name: str):
    """Return the full ``GroupRunSummary`` for one group run."""
    run_dir = _resolve_group_dir(name)
    summary_file = run_dir / "group_summary.json"
    if not summary_file.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"group_summary.json not found in {run_dir}",
        )
    try:
        data = json.loads(summary_file.read_text())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    # Attach the on-disk run directory (the orchestrator pins
    # subjects/<subject>/ underneath it) so the UI can link out.
    data["run_dir"] = str(run_dir)

    # If a group_summary.html exists alongside, advertise it for the UI
    # to open in a new tab. Path relative to the group dir.
    html_file = run_dir / "group_summary.html"
    if html_file.is_file():
        data["html_report"] = "group_summary.html"

    return data


# ─── helpers ───────────────────────────────────────────────────

def _resolve_group_dir(name: str) -> Path:
    """Reject path-traversal; resolve against the canonical group_runs root."""
    if not name or "/" in name or ".." in name or name.startswith("."):
        raise HTTPException(status_code=400, detail=f"invalid group name: {name!r}")
    return paths.group_runs_root() / name


def _summarize(run_dir: Path, data: dict) -> dict:
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
        "run_dir": str(run_dir),
        "subjects": data.get("subjects", []),
        "n_subjects": len(data.get("subjects", [])),
        "status_counts": status_counts,
        "started_at": data.get("started_at", ""),
        "finished_at": data.get("finished_at", ""),
        "total_elapsed_s": data.get("total_elapsed_s", 0.0),
        "has_html_report": (run_dir / "group_summary.html").is_file(),
    }
