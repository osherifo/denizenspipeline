"""Values that flow along analysis graph edges, beyond the core data classes."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

from fmriflow.context import PipelineContext

# Context keys the fixed-stage pipeline used for its stage outputs.
CANONICAL_KEYS: tuple[str, ...] = ("stimuli", "responses", "features", "prepared", "result")


class ContextValue(Mapping):
    """Immutable snapshot of context keys (``result``, ``analysis.*``, ...).

    Analyzers and reporters written for the fixed-stage pipeline read and
    write a shared :class:`~fmriflow.context.PipelineContext`; in a graph
    that context travels along edges as one of these, and each node gets a
    fresh ``PipelineContext`` built from it.
    """

    __slots__ = ("_data",)

    def __init__(self, data: Mapping[str, Any] | None = None) -> None:
        self._data = dict(data or {})

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __repr__(self) -> str:
        return f"ContextValue({sorted(self._data)})"

    # PipelineContext-like accessors, so key resolvers work on snapshots too.
    def has(self, key: str) -> bool:
        return key in self._data

    def get(self, key: str, default: Any = None) -> Any:  # type: ignore[override]
        return self._data.get(key, default)

    def merged(self, *others: Mapping[str, Any]) -> ContextValue:
        """New snapshot with ``others`` layered on top, later ones winning."""
        out = dict(self._data)
        for other in others:
            out.update(other)
        return ContextValue(out)

    def to_context(self, config: dict) -> PipelineContext:
        ctx = PipelineContext(config)
        for key, value in self._data.items():
            ctx.put(key, value)
        return ctx

    @classmethod
    def from_context(cls, ctx: PipelineContext) -> ContextValue:
        return cls(ctx._store)


def merge_contexts(value: ContextValue | Iterable[Mapping[str, Any]] | None) -> ContextValue:
    """One snapshot from a single context or an ordered list of them."""
    if value is None:
        return ContextValue()
    if isinstance(value, Mapping):
        return ContextValue(value)
    out = ContextValue()
    for item in value:
        out = out.merged(item)
    return out


@dataclass
class SubjectRun:
    """One subject's run inside a fan-out: status, directory and exported context."""
    subject: str
    experiment: str = ""
    run_dir: str = ""
    status: str = "ok"
    context: ContextValue | None = None
    summary: Any = None


@dataclass
class GroupRun:
    """A group of subject runs plus group-level artifacts."""
    name: str
    label: str = ""
    run_dir: str = ""
    subjects: list[SubjectRun] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)
    summary: Any = None


@dataclass
class StudyRun:
    """Labelled groups plus study-level artifacts."""
    name: str
    groups: list[GroupRun] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)
