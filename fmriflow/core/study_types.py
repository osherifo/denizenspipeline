"""Study-scope data containers and plugin protocols.

The pipeline now has three scopes:

  Subject scope    stimuli → responses → features → prepare → model → analyze → report
  Group scope      group_collect → group_analyze → (subject_second_pass)? → group_report
  Study scope      study_collect → groups_fanout → study_analyze → study_report

``GroupOrchestrator`` fans out N subject pipelines and reduces. The new
``StudyOrchestrator`` fans out M groups and reduces across them — same
shape, one level up.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from fmriflow.core.group_types import GroupResult


@dataclass
class StudyResult:
    """Output of a study-scope run.

    Mirrors :class:`GroupResult` one level up: holds the per-group
    results plus a key-value store for study-level artifacts (typically
    cross-group δ-maps, Cohen's d fields, comparison summaries).

    ``groups`` is ordered to match the study config's ``groups:`` list;
    each ``GroupResult.study_label`` is set by the orchestrator to the
    label that group appears under in this study (which may differ from
    the group's own ``group_name``).
    """
    study_name: str
    groups: list[GroupResult] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)
    study_summary: "StudyRunSummary | None" = None

    def put(self, key: str, value: Any) -> None:
        """Store a study-level artifact under *key*."""
        self.artifacts[key] = value

    def get(self, key: str) -> Any:
        """Retrieve a study-level artifact."""
        return self.artifacts[key]

    def has(self, key: str) -> bool:
        return key in self.artifacts

    def group(self, label: str) -> GroupResult:
        """Return the GroupResult registered under *label*.

        Raises ``KeyError`` with a list of known labels if the lookup
        fails — helpful for plugin authors whose config has a typo in
        the ``a:`` / ``b:`` reference.
        """
        for g in self.groups:
            if getattr(g, "study_label", None) == label:
                return g
        labels = [getattr(g, "study_label", g.group_name) for g in self.groups]
        raise KeyError(
            f"Group label '{label}' not in study; known labels: {labels}"
        )

    def groups_by_status(self, status: str) -> list[GroupResult]:
        """All groups whose overall status matches (rolled up across subjects)."""
        out: list[GroupResult] = []
        for g in self.groups:
            if g.group_summary is None:
                continue
            statuses = {
                sr.status for s in g.subjects
                for sr in (s.run_summary.stages if s.run_summary else [])
            }
            if status == "failed" and "failed" in statuses:
                out.append(g)
            elif status == "ok" and statuses and "failed" not in statuses:
                out.append(g)
        return out


# ─── Plugin protocols ─────────────────────────────────────────────


@runtime_checkable
class StudyAnalyzer(Protocol):
    """Reduces per-group results into a study-level artifact.

    Mirrors the group-scope :class:`GroupAnalyzer` protocol one level
    up. Reads from ``StudyResult.groups`` (each carries that group's
    artifacts and — when present — its subjects' in-memory contexts)
    and writes ``study.*`` keys via ``study.put``.
    """

    name: str

    # Reserved for the v2 groups_second_pass mechanic — symmetric to
    # GroupAnalyzer.produces_subject_artifact. Not consulted in v1.
    produces_group_artifact: bool

    def analyze(self, study: StudyResult, config: dict) -> None:
        """Read per-group results and store study artifacts via study.put()."""
        ...

    def group_bindings(self, study: StudyResult) -> dict[str, Any]:
        """Bindings to inject into each group's context for the second pass.

        Only consulted when ``produces_group_artifact`` is True.
        Reserved for v2; v1 implementations return ``{}``.
        """
        return {}

    def validate_config(self, config: dict) -> list[str]:
        ...


@runtime_checkable
class StudyReporter(Protocol):
    """Renders study artifacts to final outputs (HTML, flatmaps, tables)."""

    name: str

    def report(self, study: StudyResult, config: dict) -> dict[str, str]:
        """Return a mapping of artifact label → path-or-url."""
        ...

    def validate_config(self, config: dict) -> list[str]:
        ...


# Forward declaration so ``study_summary`` annotation resolves. The real
# definition lives in :mod:`fmriflow.core.run_summary` to keep the dataclass
# next to its peers.
from fmriflow.core.run_summary import StudyRunSummary  # noqa: E402,F401
