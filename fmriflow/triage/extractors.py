"""Per-stage extractors.

Each stage writes its error context to slightly different places:

* **convert (heudiconv)** — no crash files, all signal lives in
  ``stdout.log`` and ``handle.error``.
* **preproc (fmriprep)** — nipype writes
  ``{output_dir}/sub-{subj}/log/<ts>/crash-*.txt`` for every failed
  node, which is the richest source of context.
* **autoflatten** — errors come from FreeSurfer binaries
  (``mri_label2label`` etc.) or pycortex; the signal is in stdout.
* **analysis** — last Python traceback in stdout, plus
  ``run_summary.json:stages[].detail`` for the failed stage.
* **workflow** — delegated to the failing child stage.

Public API: :func:`extract_for_kind` dispatches to the right adapter.
Adapters are pure functions — they read files, produce an
:class:`ErrorCapture`, and don't touch the run registry themselves.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from fmriflow.triage.capture import (
    ErrorCapture,
    Fingerprint,
    now_iso,
    read_tail,
)
from fmriflow.triage.scrub import scrub_text

logger = logging.getLogger(__name__)


# ── Common helpers ──────────────────────────────────────────────────────

# Python-style traceback header — regex that matches the last
# "Traceback (most recent call last):" block in a log.
_PY_TRACEBACK_RE = re.compile(
    r"Traceback \(most recent call last\):.*?(?=\nTraceback |\n{2,}|\Z)",
    re.DOTALL,
)

# Exception-line pattern — `ExceptionClass: message` at the end of
# a traceback. Matches both plain `RuntimeError: foo` and fully
# qualified `nipype.pipeline.engine.nodes.NodeExecutionError: foo`.
# We capture the class + message as separate groups so the matcher
# can search on the class + message pair specifically.
_EXCEPTION_LINE_RE = re.compile(
    r"^(?P<cls>[A-Za-z_][\w.]*(?:Error|Exception|Warning))"
    r":\s*(?P<msg>.+)$",
    re.MULTILINE,
)


def _last_traceback(text: str) -> str:
    """Return the last Python traceback block in ``text``, or the last
    ~40 lines if no traceback was found (so there's still signal)."""
    matches = _PY_TRACEBACK_RE.findall(text)
    if matches:
        return matches[-1].strip()
    # Fallback: last 40 lines.
    lines = text.splitlines()
    return "\n".join(lines[-40:])


def _exception_lines(text: str) -> list[str]:
    """Return every ``ExceptionClass: message`` line in ``text``,
    newest last. Useful as fingerprint candidates."""
    out = []
    for m in _EXCEPTION_LINE_RE.finditer(text):
        cls = m.group("cls")
        msg = m.group("msg").strip()
        out.append(f"{cls}: {msg}")
    return out


def _build_common_fingerprints(
    *,
    handle_error: str | None,
    stdout_tail: str,
    extra_ids: list[str],
) -> list[Fingerprint]:
    """Fingerprints that apply to every stage.

    We emit three kinds:
      * ``handle_error`` — the manager's pre-formatted error string.
      * ``exception_line`` — one per ``ExceptionClass: message`` line
        found in the stdout tail (Python or otherwise).
      * ``stdout_tail`` — the full scrubbed tail (single fingerprint),
        so the matcher can hit on subprocess-log signatures that aren't
        Python tracebacks (e.g. fmriprep's ``fs-check-version`` output).

    The stdout_tail fingerprint's snippet is still capped by
    ``Fingerprint.from_text`` to keep ``triage.json`` small; the full
    scrubbed tail is captured separately on the ErrorCapture itself.
    """
    fps: list[Fingerprint] = []
    if handle_error:
        fps.append(Fingerprint.from_text(
            "handle_error", handle_error, extra_ids=extra_ids,
        ))
    # Dedupe exception lines by their scrubbed text.
    seen: set[str] = set()
    for line in _exception_lines(stdout_tail):
        if line in seen:
            continue
        seen.add(line)
        fps.append(Fingerprint.from_text(
            "exception_line", line, extra_ids=extra_ids,
        ))
    if stdout_tail:
        fps.append(Fingerprint.from_text(
            "stdout_tail", stdout_tail, extra_ids=extra_ids,
        ))
    return fps


# ── Extractors ──────────────────────────────────────────────────────────

def _extract_from_state_and_log(
    *,
    run_id: str,
    kind: str,
    stage: str,
    backend: str | None,
    state: dict,
    log_path: Path | None,
    tags: list[str],
    extra_ids: list[str],
    extra_fps: list[Fingerprint] | None = None,
    crash_files: list[str] | None = None,
) -> ErrorCapture:
    """Generic extractor. Individual stage adapters call this with
    stage-specific crash files + extra fingerprints already pulled."""
    stdout_text = read_tail(log_path, max_bytes=8192) if log_path else ""
    traceback_tail = _last_traceback(stdout_text)

    handle_error = state.get("error") or ""
    # Symptom: prefer handle.error (it's short + pre-formatted), fall
    # back to the first line of the last traceback.
    symptom = handle_error or (traceback_tail.splitlines()[0] if traceback_tail else "")

    fps = _build_common_fingerprints(
        handle_error=handle_error,
        stdout_tail=stdout_text,
        extra_ids=extra_ids,
    )
    if extra_fps:
        fps.extend(extra_fps)

    return ErrorCapture(
        run_id=run_id,
        kind=kind,
        stage=stage,
        backend=backend,
        captured_at=now_iso(),
        failed_at=state.get("finished_at"),
        symptom=scrub_text(symptom, extra_ids=extra_ids),
        traceback_tail=scrub_text(traceback_tail, extra_ids=extra_ids),
        stdout_tail=scrub_text(stdout_text, extra_ids=extra_ids),
        crash_files=[scrub_text(p, extra_ids=extra_ids) for p in (crash_files or [])],
        fingerprints=fps,
        candidate_matches=[],
        tags=tags,
    )


def _extract_convert(run_id: str, state: dict, log_path: Path | None) -> ErrorCapture:
    backend = state.get("backend") or "heudiconv"
    subject = state.get("subject") or ""
    return _extract_from_state_and_log(
        run_id=run_id,
        kind="convert",
        stage="convert",
        backend=backend,
        state=state,
        log_path=log_path,
        tags=["convert", backend],
        extra_ids=[subject] if subject else [],
    )


def _find_fmriprep_crash_files(output_dir: Path, subject: str) -> list[Path]:
    """fmriprep writes nipype crash files under:
        {output_dir}/sub-{subject}/log/<timestamp>/crash-*.txt
    Newest last."""
    if not output_dir or not subject:
        return []
    sub_log_dir = output_dir / f"sub-{subject}" / "log"
    if not sub_log_dir.is_dir():
        return []
    crashes = []
    for ts_dir in sorted(sub_log_dir.iterdir()):
        if not ts_dir.is_dir():
            continue
        crashes.extend(sorted(ts_dir.glob("crash-*.txt")))
        crashes.extend(sorted(ts_dir.glob("crash-*.pklz")))  # nipype's pickled variant
    # Limit to last 5 so triage stays compact even on a catastrophic run.
    return crashes[-5:]


def _extract_preproc(run_id: str, state: dict, log_path: Path | None) -> ErrorCapture:
    backend = state.get("backend") or "fmriprep"
    subject = state.get("subject") or ""
    params = state.get("params") or {}
    output_dir = params.get("output_dir")
    crash_paths: list[Path] = []
    crash_snippets: list[str] = []
    if backend == "fmriprep" and output_dir and subject:
        crash_paths = _find_fmriprep_crash_files(Path(output_dir), subject)
        for cp in crash_paths:
            try:
                # Crash files can be large; we only want the Traceback
                # block and a couple of context lines.
                text = read_tail(cp, max_bytes=4096)
                crash_snippets.append(text)
            except OSError:
                continue

    # One fingerprint per crash file, separate from stdout_tail so the
    # matcher can weight them differently if needed.
    extra_fps = [
        Fingerprint.from_text(
            "crash_file", snippet, extra_ids=[subject] if subject else [],
        )
        for snippet in crash_snippets
        if snippet
    ]

    return _extract_from_state_and_log(
        run_id=run_id,
        kind="preproc",
        stage="preproc",
        backend=backend,
        state=state,
        log_path=log_path,
        tags=["preproc", backend],
        extra_ids=[subject] if subject else [],
        extra_fps=extra_fps,
        crash_files=[str(p) for p in crash_paths],
    )


def _extract_autoflatten(run_id: str, state: dict, log_path: Path | None) -> ErrorCapture:
    backend = state.get("backend") or "autoflatten"
    subject = state.get("subject") or ""
    return _extract_from_state_and_log(
        run_id=run_id,
        kind="autoflatten",
        stage="autoflatten",
        backend=backend,
        state=state,
        log_path=log_path,
        tags=["autoflatten", backend],
        extra_ids=[subject] if subject else [],
    )


def _extract_analysis(run_id: str, state: dict, log_path: Path | None) -> ErrorCapture:
    """Analysis runs also have a run_summary.json with per-stage detail;
    include any failed-stage detail strings as extra fingerprints."""
    backend = state.get("backend") or "pipeline"
    subject = state.get("subject") or ""
    params = state.get("params") or {}
    output_dir = params.get("output_dir")

    extra_fps: list[Fingerprint] = []
    if output_dir:
        summary_path = Path(output_dir) / "run_summary.json"
        if summary_path.is_file():
            try:
                data = json.loads(summary_path.read_text())
                for s in data.get("stages", []):
                    if s.get("status") == "failed" and s.get("detail"):
                        extra_fps.append(Fingerprint.from_text(
                            f"stage_detail:{s.get('name', '?')}",
                            s["detail"],
                            extra_ids=[subject] if subject else [],
                        ))
            except (OSError, json.JSONDecodeError):
                logger.debug("Could not parse run_summary.json at %s", summary_path, exc_info=True)

    return _extract_from_state_and_log(
        run_id=run_id,
        kind="run",
        stage="analysis",
        backend=backend,
        state=state,
        log_path=log_path,
        tags=["analysis", backend],
        extra_ids=[subject] if subject else [],
        extra_fps=extra_fps,
    )


# ── Dispatch ────────────────────────────────────────────────────────────

_EXTRACTORS = {
    "convert": _extract_convert,
    "preproc": _extract_preproc,
    "autoflatten": _extract_autoflatten,
    "run": _extract_analysis,          # the analysis stage's registry kind is "run"
    "analysis": _extract_analysis,
}


def extract_for_kind(
    run_id: str,
    kind: str,
    state: dict,
    log_path: Path | str | None,
) -> ErrorCapture:
    """Dispatch to the right stage extractor.

    ``kind`` is ``state['kind']`` from the RunStateFile — the same
    string the registry uses. "workflow" is NOT handled here; workflow
    triage extracts the failing child stage instead (see
    ``WorkflowManager`` hook).
    """
    extractor = _EXTRACTORS.get(kind)
    if extractor is None:
        logger.warning("No triage extractor for kind=%r; using generic", kind)
        # Fall back to the generic extractor so we still capture *something*.
        return _extract_from_state_and_log(
            run_id=run_id,
            kind=kind,
            stage=kind,
            backend=state.get("backend"),
            state=state,
            log_path=Path(log_path) if log_path else None,
            tags=[kind],
            extra_ids=[state.get("subject") or ""],
        )
    return extractor(run_id, state, Path(log_path) if log_path else None)
