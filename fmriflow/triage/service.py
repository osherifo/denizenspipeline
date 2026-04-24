"""The triage() entry point — called by each manager when a run
transitions to ``failed``.

Usage from a manager:

    from fmriflow.triage import service as triage_svc

    def _persist_state(self, handle):
        ...existing persist code...
        if handle.status == "failed":
            triage_svc.triage_async(
                run_id=handle.run_id,
                kind="preproc",          # or "convert", "autoflatten", "run"
                registry=self.registry,
            )

The ``_async`` variant fires on a daemon thread so the manager's
shutdown path never blocks on I/O. For synchronous use (tests, CLI
scan, retroactive triage) call :func:`triage` directly.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

from fmriflow.triage.capture import ErrorCapture, TriageFileName
from fmriflow.triage.extractors import extract_for_kind
from fmriflow.triage.matcher import match_capture

logger = logging.getLogger(__name__)


def triage(
    *,
    run_id: str,
    kind: str,
    state: dict[str, Any] | None = None,
    run_dir: Path | str | None = None,
    log_path: Path | str | None = None,
) -> ErrorCapture | None:
    """Extract + match + persist triage.json for a single failed run.

    At least one of (state, run_dir, log_path) must let us locate the
    run's on-disk footprint. In practice, managers pass ``state`` and
    let this function derive the rest.

    Returns the built :class:`ErrorCapture`, or ``None`` if triage
    couldn't run (e.g. no state file found).
    """
    # Resolve state + paths.
    if state is None and run_dir is not None:
        state = _load_state_from_dir(Path(run_dir), run_id)
    if state is None:
        logger.warning("triage(%s): no state available, skipping", run_id)
        return None

    # Derive log_path from state.stdout_log if not given.
    if log_path is None:
        log_path = state.get("stdout_log")
    if log_path is None and run_dir:
        log_path = Path(run_dir) / "stdout.log"

    # Extract.
    try:
        capture = extract_for_kind(run_id, kind, state, log_path)
    except Exception:
        logger.warning("triage(%s): extractor crashed", run_id, exc_info=True)
        return None

    # Match.
    try:
        matches = match_capture(capture)
    except Exception:
        logger.warning("triage(%s): matcher crashed", run_id, exc_info=True)
        matches = []

    # ErrorCapture is frozen; rebuild it with matches attached.
    data = capture.to_dict()
    data["candidate_matches"] = [
        {
            "id": m.id,
            "title": m.title,
            "confidence": m.confidence,
            "match_on": m.match_on,
            "matched_fingerprint_hashes": list(m.matched_fingerprint_hashes),
        }
        for m in matches
    ]
    capture = ErrorCapture.from_dict(data)

    # Persist alongside state.json.
    triage_path = _triage_path_for(state, run_dir, run_id)
    if triage_path is not None:
        try:
            capture.save(triage_path)
            logger.info(
                "triage(%s): wrote %s (%d matches)",
                run_id, triage_path, len(matches),
            )
        except OSError:
            logger.warning("triage(%s): could not write %s", run_id, triage_path, exc_info=True)

    return capture


def triage_async(
    *,
    run_id: str,
    kind: str,
    state: dict[str, Any] | None = None,
    run_dir: Path | str | None = None,
    log_path: Path | str | None = None,
) -> None:
    """Fire-and-forget wrapper. Runs :func:`triage` on a daemon thread
    so the caller's shutdown path never blocks."""

    def _run():
        try:
            triage(
                run_id=run_id, kind=kind, state=state,
                run_dir=run_dir, log_path=log_path,
            )
        except Exception:
            logger.warning("triage_async(%s) failed", run_id, exc_info=True)

    t = threading.Thread(
        target=_run, daemon=True, name=f"triage-{run_id}",
    )
    t.start()


# Track which runs have already been triaged so managers can call
# ``trigger_on_failure`` on every ``_persist_state`` without firing
# triage repeatedly as status bounces ``running -> failed`` back and
# forth across events. Process-local is enough — if the server
# restarts, the reattach path will see that triage.json already
# exists on disk and skip re-running it.
_triage_fired: set[str] = set()
_triage_fired_lock = threading.Lock()


def trigger_on_failure(
    *,
    run_id: str,
    kind: str,
    status: str,
    state: dict[str, Any] | None = None,
    run_dir: Path | str | None = None,
    log_path: Path | str | None = None,
) -> bool:
    """Idempotent entry point for managers to call from ``_persist_state``.

    Fires triage exactly once per ``run_id`` when ``status`` is
    ``"failed"``. Returns True if triage was fired, False otherwise
    (wrong status, or already fired for this run).
    """
    if status != "failed":
        return False
    with _triage_fired_lock:
        if run_id in _triage_fired:
            return False
        _triage_fired.add(run_id)
    triage_async(
        run_id=run_id, kind=kind, state=state,
        run_dir=run_dir, log_path=log_path,
    )
    return True


# ── Helpers ──────────────────────────────────────────────────────────────

def _load_state_from_dir(run_dir: Path, run_id: str) -> dict | None:
    """Read state.json from a run directory. Returns None if missing."""
    state_file = run_dir / "state.json"
    if not state_file.is_file():
        return None
    try:
        return json.loads(state_file.read_text())
    except (OSError, json.JSONDecodeError):
        logger.debug("Could not parse %s", state_file, exc_info=True)
        return None


def _triage_path_for(
    state: dict,
    run_dir: Path | str | None,
    run_id: str,
) -> Path | None:
    """Pick where to write triage.json. Prefer the directory that
    contains state.json; fall back to ~/.fmriflow/runs/{run_id}/ if
    we can figure out the registry root.
    """
    # If stdout_log is a full path inside the registry, use its parent.
    log = state.get("stdout_log")
    if log:
        parent = Path(log).parent
        if parent.is_dir():
            return parent / TriageFileName

    if run_dir:
        rd = Path(run_dir)
        if rd.is_dir():
            return rd / TriageFileName

    # Last resort: the default registry path.
    default = Path.home() / ".fmriflow" / "runs" / run_id
    default.mkdir(parents=True, exist_ok=True)
    return default / TriageFileName
