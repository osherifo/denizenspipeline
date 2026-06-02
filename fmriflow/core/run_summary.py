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
class NodeRecord:
    """One plugin invocation within a stage.

    Recorded by the orchestrator so the run-graph viewer can show
    accurate per-plugin status, timing, and (for reporters) the files
    that plugin wrote — instead of inheriting the surrounding stage's
    status as a coarse approximation.

    ``id`` matches the node ID the graph builder generates (e.g.
    ``features:english1000``, ``report:flatmap#2`` when a name repeats)
    so the frontend can pair recorded nodes with config-derived ones
    on the same key.
    """
    id: str
    kind: str          # 'stimulus_loader' | 'reporter' | …
    name: str          # plugin name as it appears in config
    status: str        # 'ok' | 'failed' | 'warning' | 'skipped'
    elapsed_s: float
    detail: str = ''
    # File paths produced by this plugin, RELATIVE to the run's
    # output_dir when possible (absolute when the file lives outside
    # output_dir, which happens occasionally for shared caches).
    outputs: list[str] = field(default_factory=list)


@dataclass
class StageRecord:
    """Timing and status for a single pipeline stage."""
    name: str
    status: str          # "ok" | "warning" | "failed" | "skipped"
    elapsed_s: float
    detail: str
    # Per-plugin breakdown. Empty for stages that have no plugins
    # configured, and empty on older summaries that pre-date this
    # field — the run-graph builder treats absence as "fall back to
    # stage-level status for every config-derived plugin".
    nodes: list[NodeRecord] = field(default_factory=list)


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
            stages=[_stage_from_dict(s) for s in data.get('stages', [])],
            config_snapshot=data.get('config_snapshot', {}),
        )


def _stage_from_dict(s: dict) -> StageRecord:
    """Hydrate a StageRecord, tolerating older summaries lacking ``nodes``."""
    nodes_raw = s.get('nodes') or []
    nodes = [_node_from_dict(n) for n in nodes_raw if isinstance(n, dict)]
    return StageRecord(
        name=s.get('name', ''),
        status=s.get('status', 'unknown'),
        elapsed_s=s.get('elapsed_s', 0.0),
        detail=s.get('detail', '') or '',
        nodes=nodes,
    )


def _node_from_dict(n: dict) -> NodeRecord:
    return NodeRecord(
        id=n.get('id', ''),
        kind=n.get('kind', ''),
        name=n.get('name', ''),
        status=n.get('status', 'unknown'),
        elapsed_s=n.get('elapsed_s', 0.0),
        detail=n.get('detail', '') or '',
        outputs=list(n.get('outputs') or []),
    )


class NodeIdGen:
    """Generate unique node IDs within one stage scope.

    Mirrors the suffixing rule in
    :func:`fmriflow.server.services.run_graph._subject_plugin_nodes`
    so a NodeRecord written by the orchestrator pairs up with a
    config-derived plugin node on the same key.
    """

    def __init__(self, stage: str):
        self._stage = stage
        self._seen: dict[str, int] = {}

    def make(self, name: str) -> str:
        base = f'{self._stage}:{name}'
        n = self._seen.get(base, 0)
        self._seen[base] = n + 1
        return base if n == 0 else f'{base}#{n + 1}'


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
    # Path-safe ISO-ish UTC stamp generated when the orchestrator instance
    # is created. Empty for older summaries that pre-date the run-id layout.
    run_id: str = ""

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
                    stages=[_stage_from_dict(st) for st in s.get('stages', [])],
                    config_snapshot=s.get('config_snapshot', {}),
                )
                for s in data.get('subject_summaries', [])
            ],
            group_stages=[_stage_from_dict(s) for s in data.get('group_stages', [])],
            config_snapshot=data.get('config_snapshot', {}),
            run_id=data.get('run_id', ''),
        )
