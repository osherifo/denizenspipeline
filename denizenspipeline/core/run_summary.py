"""RunSummary — lightweight record of a pipeline execution."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


def fmt_time(seconds: float) -> str:
    """Format seconds into a human-friendly string."""
    if seconds >= 3600:
        h = seconds / 3600
        return f"{h:.1f}h"
    if seconds >= 60:
        m = seconds / 60
        return f"{m:.1f}m"
    return f"{seconds:.1f}s"


@dataclass
class StageRecord:
    """Timing and status for a single pipeline stage."""
    name: str
    status: str          # "ok" | "warning" | "failed" | "skipped"
    elapsed_s: float
    detail: str


@dataclass
class RunSummary:
    """Complete record of a pipeline run."""
    experiment: str
    subject: str
    started_at: str      # ISO timestamp
    finished_at: str
    total_elapsed_s: float
    stages: list[StageRecord] = field(default_factory=list)
    config_snapshot: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    def save_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
