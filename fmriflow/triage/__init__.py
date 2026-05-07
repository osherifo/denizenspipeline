"""Automatic error capture — extracts structured failure records from
failed runs, matches them against the error knowledge base, and
writes a triage.json next to the run's state.json.

See devdocs/proposals/infrastructure/automatic-error-capture.md.
"""

from fmriflow.triage.capture import (
    ErrorCapture,
    Fingerprint,
    CandidateMatch,
    TriageFileName,
)
from fmriflow.triage.scrub import scrub_text

__all__ = [
    "ErrorCapture",
    "Fingerprint",
    "CandidateMatch",
    "TriageFileName",
    "scrub_text",
]
