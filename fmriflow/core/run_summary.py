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

    @classmethod
    def from_json(cls, path: Path) -> RunSummary:
        """Load a RunSummary from a JSON file."""
        with open(path) as f:
            data = json.load(f)
        return cls(
            experiment=data.get('experiment', ''),
            subject=data.get('subject', ''),
            started_at=data.get('started_at', ''),
            finished_at=data.get('finished_at', ''),
            total_elapsed_s=data.get('total_elapsed_s', 0.0),
            stages=[StageRecord(**s) for s in data.get('stages', [])],
            config_snapshot=data.get('config_snapshot', {}),
        )


@dataclass
class GroupRunSummary:
    """Complete record of a group-scope pipeline run.

    Aggregates one :class:`RunSummary` per subject plus stage records
    for the group-scope stages themselves (``group_collect``,
    ``group_analyze``, ``subject_second_pass``, ``group_report``).
    """
    group_name: str
    subjects: list[str]
    started_at: str
    finished_at: str
    total_elapsed_s: float
    subject_summaries: list[RunSummary] = field(default_factory=list)
    group_stages: list[StageRecord] = field(default_factory=list)
    config_snapshot: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    def save_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def from_json(cls, path: Path) -> GroupRunSummary:
        with open(path) as f:
            data = json.load(f)
        return cls(
            group_name=data.get('group_name', ''),
            subjects=data.get('subjects', []),
            started_at=data.get('started_at', ''),
            finished_at=data.get('finished_at', ''),
            total_elapsed_s=data.get('total_elapsed_s', 0.0),
            subject_summaries=[
                RunSummary(
                    experiment=s.get('experiment', ''),
                    subject=s.get('subject', ''),
                    started_at=s.get('started_at', ''),
                    finished_at=s.get('finished_at', ''),
                    total_elapsed_s=s.get('total_elapsed_s', 0.0),
                    stages=[StageRecord(**st) for st in s.get('stages', [])],
                    config_snapshot=s.get('config_snapshot', {}),
                )
                for s in data.get('subject_summaries', [])
            ],
            group_stages=[StageRecord(**s) for s in data.get('group_stages', [])],
            config_snapshot=data.get('config_snapshot', {}),
        )
