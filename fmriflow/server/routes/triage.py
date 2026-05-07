"""Triage endpoints — serve triage.json for failed runs and let the
UI save a new error entry pre-filled from a capture.

Draft entries go to ``devdocs/errors/_proposed/`` — gitignored for now
(devdocs/ as a whole is gitignored per CLAUDE.md). Once the user
reviews a draft, they move it into ``devdocs/errors/`` proper by
renaming, at which point the errors-route scan picks it up.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from fmriflow.server.services.run_registry import RunRegistry
from fmriflow.triage.capture import ErrorCapture, TriageFileName
from fmriflow.triage.service import triage as triage_sync

logger = logging.getLogger(__name__)
router = APIRouter(tags=["triage"])


# Draft error YAMLs land here. Mirrors ``devdocs/errors/`` structure so
# promoting a draft to a real KB entry is just a mv.
_ERRORS_DIR = Path(__file__).resolve().parents[3] / "devdocs" / "errors"
_PROPOSED_DIR = _ERRORS_DIR / "_proposed"


# ── Request models ──────────────────────────────────────────────────────

class FromCaptureBody(BaseModel):
    """Fields the user has edited in the pre-filled error form.

    ``run_id`` is required so the server can locate the capture; the
    other fields override what the auto-extractor filled in.
    """

    run_id: str
    title: str
    tags: list[str] = []
    root_cause: str = ""
    fix: str = ""
    references: list[str] = []
    # Optional slug (lowercase, underscore-separated) for the filename.
    slug: str | None = None


# ── Endpoints ───────────────────────────────────────────────────────────

@router.get("/triage/{run_id}")
async def get_triage(run_id: str):
    """Return the triage.json for a run if it exists.

    Returns 404 if the run has no triage record yet — the UI should
    treat this as "no matches" rather than an error. Still-running or
    successful runs have no triage.json by design.
    """
    registry = RunRegistry()
    triage_path = registry.run_dir(run_id) / TriageFileName
    if not triage_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"No triage record for run '{run_id}'",
        )
    try:
        return json.loads(triage_path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise HTTPException(status_code=500, detail=f"Could not read triage.json: {e}")


@router.post("/triage/{run_id}/rescan")
async def rescan_triage(run_id: str):
    """Re-run the extractor + matcher against an existing run.

    Useful after the KB grows new fingerprints that might
    retroactively match an older capture. Overwrites the existing
    triage.json.
    """
    registry = RunRegistry()
    state = registry.load(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    capture = triage_sync(
        run_id=run_id,
        kind=state.kind,
        state=state.to_dict(),
        run_dir=registry.run_dir(run_id),
    )
    if capture is None:
        raise HTTPException(status_code=500, detail="Extractor returned no capture")
    return capture.to_dict()


@router.post("/errors/from-capture")
async def new_error_from_capture(body: FromCaptureBody):
    """Write a pre-filled error draft YAML under ``devdocs/errors/_proposed/``.

    The draft inherits everything the auto-extractor captured —
    symptom, traceback tail, fingerprints — and layers user-supplied
    title / root_cause / fix on top. Once the user is happy with the
    draft, they move it into the parent ``devdocs/errors/`` dir (plain
    ``mv``) and it becomes a real KB entry.
    """
    registry = RunRegistry()
    triage_path = registry.run_dir(body.run_id) / TriageFileName
    if not triage_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"No triage record for run '{body.run_id}' — cannot pre-fill draft",
        )
    try:
        capture = ErrorCapture.from_json(triage_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not parse triage.json: {e}")

    next_id = _next_available_id()
    slug = body.slug or _slug_from_title(body.title) or f"run_{body.run_id[:8]}"
    filename = f"{next_id:04d}_{slug}.yaml"

    draft_yaml = _render_draft_yaml(
        id_=next_id,
        title=body.title,
        tags=body.tags or capture.tags,
        stage=capture.stage,
        root_cause=body.root_cause,
        fix=body.fix,
        references=body.references,
        capture=capture,
    )

    _PROPOSED_DIR.mkdir(parents=True, exist_ok=True)
    out = _PROPOSED_DIR / filename
    if out.exists():
        raise HTTPException(
            status_code=409,
            detail=f"Draft already exists: {out.name}",
        )
    try:
        out.write_text(draft_yaml)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Write failed: {e}")

    return {
        "saved": True,
        "id": next_id,
        "filename": filename,
        "path": str(out.resolve()),
        "proposed_dir": str(_PROPOSED_DIR.resolve()),
    }


# ── Helpers ─────────────────────────────────────────────────────────────

def _next_available_id() -> int:
    """Find the next unused error id across both the KB and the
    proposed-drafts dir."""
    max_id = 0
    for d in (_ERRORS_DIR, _PROPOSED_DIR):
        if not d.is_dir():
            continue
        for p in d.glob("*.yaml"):
            stem = p.stem
            prefix = stem.split("_", 1)[0]
            if prefix.isdigit():
                max_id = max(max_id, int(prefix))
    return max_id + 1


def _slug_from_title(title: str) -> str:
    """Lowercase slug for use in a filename."""
    if not title:
        return ""
    cleaned = "".join(c if c.isalnum() or c in " -_" else " " for c in title.lower())
    return "_".join(cleaned.split())[:60].strip("_")


def _render_draft_yaml(
    *,
    id_: int,
    title: str,
    tags: list[str],
    stage: str,
    root_cause: str,
    fix: str,
    references: list[str],
    capture: ErrorCapture,
) -> str:
    """Render the draft YAML. We hand-roll the string (rather than
    yaml.dump) so multi-line blocks use the ``|`` scalar style that
    existing KB entries follow — it round-trips cleanly when the user
    edits the file."""
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    tag_yaml = "[" + ", ".join(tags) + "]" if tags else "[]"

    # Fingerprints section — auto-suggested from the capture's
    # exception_line fingerprints as a starting point.
    fp_block_lines: list[str] = []
    for fp in capture.fingerprints:
        if fp.source == "exception_line":
            fp_block_lines.append(
                f"  - source: {fp.source}\n"
                f"    regex: {_quote_for_yaml_regex(fp.snippet)}"
            )
    fp_block = "\n".join(fp_block_lines) or "  # Add fingerprints here — target ExceptionClass: message patterns."

    refs_block = "\n".join(f"  - {_quote_yaml_string(r)}" for r in references) or "  # add references here"

    symptom_block = _indent_block(capture.symptom or "(no symptom captured)", "  ")
    traceback_block = _indent_block(capture.traceback_tail or "(no traceback captured)", "  ")

    return (
        f"# DRAFT — generated from triage for run {capture.run_id}\n"
        f"# Move to devdocs/errors/ once reviewed.\n"
        f"\n"
        f"id: {id_}\n"
        f"title: {_quote_yaml_string(title)}\n"
        f"date: {date}\n"
        f"author: \n"
        f"stage: {stage}\n"
        f"tags: {tag_yaml}\n"
        f"\n"
        f"symptoms: |\n"
        f"{symptom_block}\n"
        f"\n"
        f"  === traceback tail (scrubbed) ===\n"
        f"{traceback_block}\n"
        f"\n"
        f"root_cause: |\n"
        f"{_indent_block(root_cause or '(fill this in)', '  ')}\n"
        f"\n"
        f"fix: |\n"
        f"{_indent_block(fix or '(fill this in)', '  ')}\n"
        f"\n"
        f"references:\n"
        f"{refs_block}\n"
        f"\n"
        f"fingerprints:\n"
        f"{fp_block}\n"
    )


def _indent_block(text: str, indent: str) -> str:
    return "\n".join(indent + line for line in text.splitlines())


def _quote_yaml_string(s: str) -> str:
    """Double-quote a YAML string, escaping embedded quotes."""
    escaped = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _quote_for_yaml_regex(pattern: str) -> str:
    """Wrap a regex in double quotes, preserving backslashes that
    the regex engine needs (escape each backslash for YAML's double-
    quoted string rules).
    """
    escaped = pattern.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
