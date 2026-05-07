"""PostPreprocManifest — recorded outputs of a post-preprocessing graph run."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class NodeRunRecord:
    """One executed node in a post-preproc graph run."""
    node_id: str
    node_type: str          # e.g. "smooth"
    params: dict[str, Any]
    inputs: dict[str, str]   # handle -> source file path
    outputs: dict[str, str]  # handle -> output file path
    duration_s: float | None = None


@dataclass(frozen=True)
class PostPreprocManifest:
    """Outputs and provenance for a post-preproc graph run."""

    subject: str
    dataset: str
    source_manifest_path: str  # the upstream PreprocManifest
    graph: dict[str, Any]       # ReactFlow-shape graph that produced this
    nodes_run: list[NodeRunRecord]
    output_dir: str
    created: str = field(default_factory=now_iso)
    pipeline_version: str | None = None
    manifest_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def save(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_json())
        return p

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PostPreprocManifest:
        runs = [NodeRunRecord(**r) for r in data.get("nodes_run", [])]
        clean = {k: v for k, v in data.items() if k != "nodes_run"}
        return cls(nodes_run=runs, **clean)

    @classmethod
    def from_json(cls, path: str | Path) -> PostPreprocManifest:
        return cls.from_dict(json.loads(Path(path).read_text()))


@dataclass(frozen=True)
class PostPreprocConfig:
    """Configuration for executing a post-preproc graph against a subject."""

    subject: str
    source_manifest_path: str
    graph: dict[str, Any]
    output_dir: str
    name: str | None = None  # optional user-given run name

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PostPreprocConfig:
        return cls(**data)
