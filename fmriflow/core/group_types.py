"""Group-scope data containers and plugin protocols.

The 7-stage `PipelineOrchestrator` is subject-scoped. The group scope sits
above it: a `GroupOrchestrator` fans out N subject-scope pipelines, then
runs `GroupAnalyzer` plugins that reduce the per-subject results into
group-level artifacts (cross-subject averages, shared subspaces,
consistency maps, summary statistics).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from fmriflow.context import PipelineContext
from fmriflow.core.run_summary import RunSummary


@dataclass(frozen=True)
class SubjectResult:
    """One subject-scope pipeline run, as seen from group scope.

    A thin handle: the heavy artifacts (weights, prediction maps) live
    on disk under ``run_dir``; ``context`` is populated for in-memory
    runs (the normal fan-out case) and ``None`` for runs loaded from
    disk on resume.
    """
    subject: str
    experiment: str
    run_dir: Path
    run_summary: RunSummary
    context: PipelineContext | None = None

    @property
    def status(self) -> str:
        """Top-line status of this subject's pipeline.

        Aggregated from the stage records — ``ok`` only if every stage
        completed without failure.
        """
        if not self.run_summary.stages:
            return "unknown"
        statuses = {s.status for s in self.run_summary.stages}
        if "failed" in statuses:
            return "failed"
        if "warning" in statuses:
            return "warning"
        return "ok"


@dataclass
class GroupResult:
    """Output of a group-scope run.

    Mirrors :class:`fmriflow.context.PipelineContext`'s role at the
    group level: holds the per-subject results plus a key-value store
    for group-level artifacts.

    ``study_label`` is set by ``StudyOrchestrator`` when this group is
    embedded inside a study run — it's the study-scope label this
    group appears under (which may differ from ``group_name`` since
    the same group YAML can be reused in multiple studies under
    different labels). Unset for standalone group runs.
    """
    group_name: str
    subjects: list[SubjectResult] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)
    group_summary: "GroupRunSummary | None" = None
    study_label: str | None = None

    def put(self, key: str, value: Any) -> None:
        """Store a group-level artifact under *key*."""
        self.artifacts[key] = value

    def get(self, key: str) -> Any:
        """Retrieve a group-level artifact."""
        return self.artifacts[key]

    def has(self, key: str) -> bool:
        return key in self.artifacts

    def subjects_by_status(self, status: str) -> list[SubjectResult]:
        return [sr for sr in self.subjects if sr.status == status]


# ─── Plugin protocols ─────────────────────────────────────────────

@runtime_checkable
class GroupAnalyzer(Protocol):
    """Reduces per-subject results into a group-level artifact.

    Mirrors the subject-scope ``Analyzer`` protocol but operates on
    ``GroupResult`` (which carries all subjects' contexts/results)
    instead of a single ``PipelineContext``.
    """

    name: str

    # If True, after this analyzer runs the GroupOrchestrator triggers
    # a second per-subject pass through `analyze + report` with the
    # bindings returned by ``subject_bindings`` injected into each
    # subject's PipelineContext under the ``external.*`` namespace.
    produces_subject_artifact: bool

    def analyze(self, group: GroupResult, config: dict) -> None:
        """Read per-subject results and store group artifacts via group.put()."""
        ...

    def subject_bindings(self, group: GroupResult) -> dict[str, Any]:
        """Bindings to inject into each subject's context for the second pass.

        Only consulted when ``produces_subject_artifact`` is True. Keys
        are bare names; the orchestrator prefixes them with ``external.``
        before calling ``PipelineContext.put``.
        """
        return {}

    def validate_config(self, config: dict) -> list[str]:
        ...


@runtime_checkable
class GroupReporter(Protocol):
    """Renders group artifacts to final outputs (HTML, flatmaps, tables)."""

    name: str

    def report(self, group: GroupResult, config: dict) -> dict[str, str]:
        """Return a mapping of artifact label → path-or-url."""
        ...

    def validate_config(self, config: dict) -> list[str]:
        ...
