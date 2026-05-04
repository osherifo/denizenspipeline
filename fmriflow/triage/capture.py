"""ErrorCapture — structured failure record for a single run.

Layered on top of PR #55's detach/reattach substrate. When a stage
fails, a capture is assembled from ``~/.fmriflow/runs/{run_id}/``
(state.json + stdout.log) plus stage-specific artefacts (e.g.
fmriprep's nipype ``crash-*.txt`` files), matched against the error
knowledge base, and written alongside as ``triage.json``.

See ``devdocs/proposals/infrastructure/automatic-error-capture.md``
for the design.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fmriflow.triage.scrub import scrub_text


# Name of the triage sidecar file, colocated with state.json + stdout.log.
TriageFileName = "triage.json"


@dataclass(frozen=True)
class Fingerprint:
    """A normalised signal extracted from a capture.

    ``source`` names where the snippet came from so a matcher can
    decide which stored regex to consult. ``hash`` is a stable
    SHA-256 over the raw text so we can dedupe identical captures
    across runs. ``snippet`` is the scrubbed text (first 500 chars)
    for human review.
    """

    source: str                       # e.g. "stdout_tail", "crash_file", "handle_error"
    hash: str                         # "sha256:<hexdigest>"
    snippet: str                      # scrubbed, <= 500 chars

    @classmethod
    def from_text(cls, source: str, text: str, *, extra_ids: list[str] | None = None) -> "Fingerprint":
        """Build a fingerprint from raw text. Scrubs before hashing so
        the hash is stable across users / machines."""
        scrubbed = scrub_text(text or "", extra_ids=extra_ids)
        digest = hashlib.sha256(scrubbed.encode("utf-8", errors="replace")).hexdigest()
        # Cap snippet so triage.json stays small.
        snippet = scrubbed if len(scrubbed) <= 500 else scrubbed[:500] + "…"
        return cls(source=source, hash=f"sha256:{digest}", snippet=snippet)


@dataclass(frozen=True)
class CandidateMatch:
    """A KB entry that the matcher thinks explains this capture."""

    id: int                           # error entry id (matches devdocs/errors/NNNN.yaml)
    title: str                        # entry title, for display
    confidence: float                 # [0.0, 1.0]
    match_on: str                     # short human label: "exact-regex", "weak-tag-overlap", etc.
    matched_fingerprint_hashes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ErrorCapture:
    """Structured record of a single failed run's error state.

    Everything stored here is **already scrubbed** by
    :func:`fmriflow.triage.scrub.scrub_text`. The capture is safe to
    share (modulo the open question about where the KB eventually
    gets published).
    """

    # Which run failed
    run_id: str
    kind: str                         # "run" | "preproc" | "convert" | "autoflatten" | "workflow"
    stage: str                        # same as `kind` for now; workflows will set stage to the failing child
    backend: str | None               # e.g. "fmriprep", "heudiconv", None

    # When
    captured_at: str                  # ISO-8601 UTC
    failed_at: float | None = None    # unix timestamp if known

    # Short human message (scrubbed)
    symptom: str = ""

    # The last Python ``Traceback (most recent call last)`` block
    # pulled out of stdout.log, scrubbed. Narrowed for display.
    traceback_tail: str = ""

    # Full scrubbed last ~8 KB of stdout.log. The matcher searches
    # against this so KB regexes can hit on subprocess-log signatures
    # that aren't Python tracebacks (fmriprep's fs-check-version,
    # heudiconv assertions, etc.).
    stdout_tail: str = ""

    # Relative paths to stage-specific crash files (scrubbed)
    crash_files: list[str] = field(default_factory=list)

    # Fingerprint candidates — inputs to the matcher
    fingerprints: list[Fingerprint] = field(default_factory=list)

    # Ranked candidate matches the matcher produced
    candidate_matches: list[CandidateMatch] = field(default_factory=list)

    # Free-form tags that a matcher or UI can use to narrow the
    # search (e.g. ["fmriprep", "freesurfer", "recon-all"])
    tags: list[str] = field(default_factory=list)

    # Schema version
    capture_version: int = 1

    # ── Serialisation ────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def save(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_json())
        return p

    # ── Deserialisation ──────────────────────────────────────────

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ErrorCapture":
        fps = [Fingerprint(**f) for f in data.pop("fingerprints", [])]
        cms = [CandidateMatch(**c) for c in data.pop("candidate_matches", [])]
        return cls(fingerprints=fps, candidate_matches=cms, **data)

    @classmethod
    def from_json(cls, path: str | Path) -> "ErrorCapture":
        p = Path(path)
        return cls.from_dict(json.loads(p.read_text()))


# ── Helpers ──────────────────────────────────────────────────────────────

def now_iso() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def read_tail(path: str | Path, *, max_bytes: int = 4096) -> str:
    """Read the last ``max_bytes`` of a text file and return as str.

    Returns empty string if the file doesn't exist or can't be read.
    Silently handles decoding errors ("replace" strategy) so a broken
    byte doesn't crash the capture pipeline.
    """
    p = Path(path)
    if not p.is_file():
        return ""
    try:
        size = p.stat().st_size
        start = max(0, size - max_bytes)
        with open(p, "rb") as f:
            f.seek(start)
            data = f.read()
        text = data.decode("utf-8", errors="replace")
        # If we started mid-line, drop the partial first line so the
        # output doesn't begin in the middle of a token.
        if start > 0 and "\n" in text:
            text = text.split("\n", 1)[1]
        return text
    except OSError:
        return ""
