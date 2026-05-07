"""Match an :class:`ErrorCapture` against the error knowledge base.

Schema extension to ``devdocs/errors/*.yaml`` — a new optional key:

.. code-block:: yaml

    id: 26
    title: "fmriprep fails with 'No T1w images found for participant'"
    # …existing fields…
    fingerprints:
      - source: stdout_tail
        regex: "No T1w images found for participant"
      - source: crash_file
        regex: "niworkflows/interfaces/bids\\.py.*No T1w images"

Matching rule for v1 is intentionally simple: a fingerprint *matches*
a capture if **any** of the capture's snippets matches the stored
regex. Confidence is `matching / total_stored_fingerprints`, clamped
to [0, 1]. Source-typing is informational for v1 — we match a stored
regex against every capture snippet, not just ones with the same
``source``. That stays robust to minor differences in where an error
manifests (e.g. a traceback showing up in stdout one run, in a crash
file the next).

Regex guidance: target the **exception class + message**, not
file:line info, so a fmriprep/nipype minor version bump doesn't
invalidate the match.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path

import yaml

from fmriflow.triage.capture import CandidateMatch, ErrorCapture

logger = logging.getLogger(__name__)


# Default KB location — same as the errors route uses.
_DEFAULT_KB_DIR = Path(__file__).resolve().parents[2] / "devdocs" / "errors"


# ── KB loading ──────────────────────────────────────────────────────────

_kb_cache: list[dict] | None = None
_kb_cache_mtime: float = 0.0
_kb_cache_dir: Path | None = None


def load_kb_entries(kb_dir: Path | None = None, *, force_rescan: bool = False) -> list[dict]:
    """Scan the error-YAMLs dir. Returns a list of dicts with keys
    ``id, title, tags, stage, fingerprints``.

    Caches against the max mtime of the directory so repeated calls
    are cheap; pass ``force_rescan=True`` to skip the cache.
    """
    global _kb_cache, _kb_cache_mtime, _kb_cache_dir
    kb_dir = kb_dir or _DEFAULT_KB_DIR

    if not kb_dir.is_dir():
        return []

    # Compute max mtime across all *.yaml files. Cheap O(N) stat.
    max_mtime = 0.0
    files = sorted(kb_dir.glob("*.yaml"))
    for p in files:
        try:
            m = p.stat().st_mtime
            if m > max_mtime:
                max_mtime = m
        except OSError:
            continue

    if (
        not force_rescan
        and _kb_cache is not None
        and _kb_cache_dir == kb_dir
        and _kb_cache_mtime >= max_mtime
    ):
        return _kb_cache

    entries: list[dict] = []
    for p in files:
        try:
            with open(p) as f:
                raw = yaml.safe_load(f) or {}
            if not isinstance(raw, dict):
                continue
            entries.append({
                "id": raw.get("id", p.stem),
                "title": raw.get("title", p.stem),
                "tags": raw.get("tags", []) or [],
                "stage": raw.get("stage", ""),
                "fingerprints": raw.get("fingerprints", []) or [],
                "path": str(p),
            })
        except Exception:
            logger.debug("Skipping KB entry %s", p, exc_info=True)

    _kb_cache = entries
    _kb_cache_mtime = max_mtime
    _kb_cache_dir = kb_dir
    return entries


# ── Matcher ─────────────────────────────────────────────────────────────

def _compile_or_none(pattern: str) -> re.Pattern | None:
    """Compile a regex defensively — a malformed entry shouldn't break
    the whole match pass. Returns None on failure."""
    try:
        return re.compile(pattern, re.IGNORECASE | re.DOTALL)
    except re.error as e:
        logger.warning("Bad KB regex %r: %s", pattern, e)
        return None


def match_capture(
    capture: ErrorCapture,
    *,
    kb_dir: Path | None = None,
    kb_entries: list[dict] | None = None,
    max_candidates: int = 5,
) -> list[CandidateMatch]:
    """Rank KB entries by how well they explain ``capture``.

    Pass ``kb_entries`` to match against a pre-loaded list; otherwise
    the matcher loads from ``kb_dir`` (default ``devdocs/errors/``).

    Returns at most ``max_candidates`` candidates, newest-first for ties.
    """
    entries = kb_entries if kb_entries is not None else load_kb_entries(kb_dir)
    if not entries:
        return []

    # Pre-extract every snippet from the capture. Also pre-concatenate
    # them into one blob so a KB regex that spans multiple lines (rare)
    # still matches. We deliberately match against the scrubbed
    # snippets — the KB is scrubber-aware.
    capture_snippets = [fp.snippet for fp in capture.fingerprints]
    # Also include the traceback + full stdout tail + symptom as
    # implicit snippets — many errors signal in subprocess output
    # that isn't a Python exception (fmriprep's fs-check-version,
    # heudiconv assertions, etc.).
    if capture.traceback_tail:
        capture_snippets.append(capture.traceback_tail)
    if getattr(capture, "stdout_tail", ""):
        capture_snippets.append(capture.stdout_tail)
    if capture.symptom:
        capture_snippets.append(capture.symptom)
    capture_blob = "\n".join(capture_snippets)

    results: list[tuple[float, CandidateMatch, int]] = []
    for entry in entries:
        fps = entry.get("fingerprints") or []
        if not fps:
            continue
        total = 0
        hit_indices: list[int] = []
        matched_hashes: list[str] = []
        for i, fp in enumerate(fps):
            if not isinstance(fp, dict):
                continue
            regex = fp.get("regex")
            if not regex:
                continue
            total += 1
            pattern = _compile_or_none(regex)
            if pattern is None:
                continue
            if pattern.search(capture_blob):
                hit_indices.append(i)
                # Attach the hash of whichever capture fp contains the
                # matched text (if any) for UI breadcrumbs.
                for cap_fp in capture.fingerprints:
                    if pattern.search(cap_fp.snippet):
                        matched_hashes.append(cap_fp.hash)
                        break

        if total == 0:
            continue
        # v1 confidence: hits / total. Clamp to [0, 1] for safety.
        conf = max(0.0, min(1.0, len(hit_indices) / total))
        if conf <= 0.0:
            continue

        match_on = (
            "all-fingerprints-match" if len(hit_indices) == total
            else f"{len(hit_indices)}/{total}-fingerprints-match"
        )
        candidate = CandidateMatch(
            id=int(entry["id"]) if str(entry["id"]).isdigit() else 0,
            title=str(entry.get("title") or ""),
            confidence=round(conf, 3),
            match_on=match_on,
            matched_fingerprint_hashes=matched_hashes,
        )
        # Use the KB entry's id for a stable newest-last sort; higher
        # id = newer entry when ties occur.
        order_id = candidate.id
        results.append((conf, candidate, order_id))

    # Sort: confidence DESC, then newest (higher id) first.
    results.sort(key=lambda t: (t[0], t[2]), reverse=True)
    return [c for _, c, _ in results[:max_candidates]]
