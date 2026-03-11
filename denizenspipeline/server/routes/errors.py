"""Error knowledge base endpoints — serves docs/errors/*.yaml entries."""

from __future__ import annotations

import logging
import time
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["errors"])
logger = logging.getLogger(__name__)

# Locate the errors directory relative to the repo root
_ERRORS_DIR = Path(__file__).resolve().parents[3] / "docs" / "errors"

# Simple cache
_cache: list[dict] | None = None
_cache_time: float = 0
_CACHE_TTL = 30.0


def _scan_errors() -> list[dict]:
    """Read all YAML error entries and normalise into a consistent shape."""
    global _cache, _cache_time
    now = time.time()
    if _cache is not None and (now - _cache_time) < _CACHE_TTL:
        return _cache

    entries: list[dict] = []
    if not _ERRORS_DIR.is_dir():
        logger.warning("Errors directory not found: %s", _ERRORS_DIR)
        _cache = []
        _cache_time = now
        return []

    for path in sorted(_ERRORS_DIR.glob("*.yaml")):
        try:
            with open(path) as f:
                raw = yaml.safe_load(f) or {}
            if not isinstance(raw, dict):
                continue
            entries.append(_normalise(raw, path.stem))
        except Exception:
            logger.debug("Skipping %s", path, exc_info=True)

    _cache = entries
    _cache_time = now
    return entries


def _normalise(raw: dict, stem: str) -> dict:
    """Normalise the two schema variants into a single shape."""
    # symptoms: string or list → string
    symptoms = raw.get("symptoms", "")
    if isinstance(symptoms, list):
        symptoms = "\n".join(f"- {s}" for s in symptoms)

    # root_cause(s): string or list → string
    root_cause = raw.get("root_cause") or raw.get("root_causes", "")
    if isinstance(root_cause, list):
        root_cause = "\n".join(f"- {r}" for r in root_cause)

    # fix(es): string or list → string
    fix = raw.get("fix") or raw.get("fixes", "")
    if isinstance(fix, list):
        fix = "\n".join(f"- {f}" for f in fix)

    # diagnosis: string or list → string
    diagnosis = raw.get("diagnosis", "")
    if isinstance(diagnosis, list):
        diagnosis = "\n".join(f"- {d}" for d in diagnosis)

    return {
        "id": raw.get("id", stem),
        "title": raw.get("title", stem),
        "date": str(raw.get("date", raw.get("added", ""))),
        "author": raw.get("author", ""),
        "stage": raw.get("stage", ""),
        "tags": raw.get("tags", []),
        "symptoms": symptoms.strip() if isinstance(symptoms, str) else symptoms,
        "root_cause": root_cause.strip() if isinstance(root_cause, str) else root_cause,
        "fix": fix.strip() if isinstance(fix, str) else fix,
        "diagnosis": diagnosis.strip() if isinstance(diagnosis, str) else diagnosis,
        "config_note": (raw.get("config_note") or "").strip(),
        "references": raw.get("references", []),
    }


@router.get("/errors")
async def list_errors(stage: str | None = None, tag: str | None = None, q: str | None = None):
    """List all error entries, optionally filtered."""
    entries = _scan_errors()

    if stage:
        entries = [e for e in entries if e["stage"] == stage]
    if tag:
        entries = [e for e in entries if tag in e["tags"]]
    if q:
        ql = q.lower()
        entries = [
            e for e in entries
            if ql in e["title"].lower()
            or ql in e["symptoms"].lower()
            or ql in e["root_cause"].lower()
            or ql in e["fix"].lower()
            or any(ql in t.lower() for t in e["tags"])
        ]

    return {"errors": entries, "total": len(entries)}


@router.get("/errors/{error_id}")
async def get_error(error_id: str):
    """Get a single error entry by ID."""
    entries = _scan_errors()
    for e in entries:
        if str(e["id"]) == error_id:
            return e
    raise HTTPException(status_code=404, detail=f"Error '{error_id}' not found")
