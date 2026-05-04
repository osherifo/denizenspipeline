"""StructuralQCReview — reviewer sign-off on structural preprocessing.

Reviewers inspect fmriprep + FreeSurfer structural outputs (in-browser via
niivue or out-of-browser via freeview) and record an Approve / Needs edits /
Rejected decision. One review per (dataset, subject).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


QC_STATUSES = ("pending", "approved", "needs_edits", "rejected")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class StructuralQCReview:
    """A reviewer's structural-QC decision for one subject."""

    dataset: str
    subject: str
    status: str = "pending"
    reviewer: str = ""
    timestamp: str = field(default_factory=now_iso)
    notes: str = ""
    freeview_command_used: str | None = None

    def __post_init__(self) -> None:
        if self.status not in QC_STATUSES:
            raise ValueError(
                f"status must be one of {QC_STATUSES}, got {self.status!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StructuralQCReview:
        # Tolerate unknown keys for forward-compat.
        known = {f for f in cls.__dataclass_fields__}
        clean = {k: v for k, v in data.items() if k in known}
        return cls(**clean)
