"""PHI / identifier scrubber for captured error records.

Rule: anything that leaves the local machine via ``triage.json`` or a
proposed error YAML gets run through :func:`scrub_text` first.

What counts as sensitive here:

* **Subject IDs.** BIDS paths like ``sub-AN/anat/…`` or raw strings
  like ``20150722AN`` identify a participant. Redact the id, keep the
  structural context (the ``sub-<...>`` prefix, the date pattern, the
  scan-session name) so the error is still diagnosable.
* **Home directory prefixes.** ``/home/omarsh/...`` or
  ``/Users/omarsh/...`` reveal who ran the pipeline. Replace the
  username segment with ``<user>``; keep the rest of the path so the
  "this crash was in fmriprep's ``scripts/`` dir" signal survives.
* **Email addresses.** Shouldn't appear in tracebacks, but nipype
  crash files sometimes embed git config identity. Redact conservatively.
* **Lab-specific mount points.** Paths under ``/mnt/raid/`` or
  ``phact_raid_mount`` — these encode the host institution. Keep the
  filename tail, collapse the prefix to ``<lab-data>``.

We do NOT try to be a general PII scrubber (no SSNs / phone numbers /
addresses — not the failure modes we'd hit). The goal is to make the
output safe to read on a shared screen or paste into an issue, not to
meet HIPAA.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

# ── Regex patterns ──────────────────────────────────────────────────────

# /home/<user>/... or /Users/<user>/...  (macOS / Linux home)
# Capture the segment after /home/ or /Users/ as the user name.
_HOME_PATH_RE = re.compile(r"(/home|/Users)/([^/\s]+)")

# Lab-specific mount prefixes we've seen in this codebase. Keep the
# filename tail after the prefix so "error was in X" is still readable.
_LAB_MOUNT_PREFIXES = [
    "/mnt/raid/",
    "/mnt/antares_raid/",
    "/phact_raid_mount/",
    "/mnt/gallantlab/",
]

# Email (conservative — requires an @, a TLD, and no whitespace).
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# BIDS-style subject ids: ``sub-<label>`` where label is alnum.
# We keep the ``sub-`` prefix so structural context survives, and
# redact the label. Examples: sub-AN → sub-<REDACTED>, sub-sub01 →
# sub-<REDACTED>.
_BIDS_SUB_RE = re.compile(r"\bsub-[A-Za-z0-9]+")

# Session-folder names that encode a scan date + initials, e.g.
# 20150722AN or 20130201AH. Pattern: 8 digits followed by 2–4 letters.
# This is lab-specific but common enough to catch.
_DATE_INITIALS_RE = re.compile(r"\b\d{8}[A-Z]{2,5}\b")

# Bare participant labels after ``--participant-label`` / ``-s`` /
# ``--subject`` / ``participant:`` etc. on a command line. This is a
# best-effort catch; we prefer NOT to over-redact generic strings.
# Examples of what we DO want to catch:
#   fmriprep ... --participant-label AN …
#   heudiconv ... -s AN ...
_PARTICIPANT_ARG_RE = re.compile(
    r"(--participant-label|--subject|-s|-ss|-subjid|participant:?)"
    r"[\s=]+"
    r"([A-Za-z0-9_-]+)"
)


# ── Public API ──────────────────────────────────────────────────────────

def scrub_text(
    text: str,
    *,
    extra_ids: list[str] | None = None,
) -> str:
    """Redact identifying substrings from ``text``.

    ``extra_ids`` lets a caller name specific subject / session tokens
    they want zapped regardless of whether the regexes would catch
    them. Typical use: the caller already knows ``handle.subject``,
    pass it in so every occurrence — including bare mentions in a
    traceback — gets redacted.
    """
    if not text:
        return text

    # Home directory prefix — /home/X/ or /Users/X/ → <user>/...
    text = _HOME_PATH_RE.sub(lambda m: f"{m.group(1)}/<user>", text)

    # Lab-specific mount prefixes.
    for prefix in _LAB_MOUNT_PREFIXES:
        # Keep anything AFTER the lab prefix — the file path inside
        # the lab mount is useful context. Just collapse the prefix.
        text = text.replace(prefix, "<lab-data>/")

    # Emails.
    text = _EMAIL_RE.sub("<email>", text)

    # Date-initials session folders (e.g. 20150722AN).
    text = _DATE_INITIALS_RE.sub("<session-id>", text)

    # Participant-label command-line args — run BEFORE the BIDS sub-
    # pattern so `--s sub-AN` is replaced as a whole (value pattern
    # allows dashes) and we don't get cascading partial redactions.
    def _redact_participant_arg(m: re.Match) -> str:
        flag = m.group(1)
        sep = m.group(0)[len(flag)]  # the separator char (' ' or '=')
        return f"{flag}{sep}<REDACTED>"
    text = _PARTICIPANT_ARG_RE.sub(_redact_participant_arg, text)

    # BIDS sub-<label> → sub-<REDACTED>. Anything on a command line
    # was already handled above; this catches bare mentions like
    # `.../sub-AN/anat/T1w.nii.gz`.
    text = _BIDS_SUB_RE.sub("sub-<REDACTED>", text)

    # Caller-supplied extras — literal string replacement, case-sensitive.
    # These typically include the current subject id, session label,
    # etc. Run AFTER the regex passes so the more-specific BIDS
    # pattern wins when both apply.
    if extra_ids:
        for tok in extra_ids:
            if tok and len(tok) >= 2:  # don't substitute on 1-char labels
                text = text.replace(tok, "<REDACTED>")

    return text


def scrub_path(path: str | Path) -> str:
    """Scrub a single path string. Same rules as :func:`scrub_text`."""
    return scrub_text(str(path))
