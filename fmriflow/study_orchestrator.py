"""Study runs: group collection and status rules.

``collect_study_groups`` resolves a study's ``groups:`` entries and the
``_*_status`` helpers roll group and stage outcomes up into the study status. The
runner itself is :class:`fmriflow.analysis.scope_runners.StudyGraphRunner`;
``StudyOrchestrator`` remains as its name here.
"""

from __future__ import annotations

import copy
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import yaml

from fmriflow import ui as fui
from fmriflow.core import paths
from fmriflow.core.group_types import GroupResult
from fmriflow.core.log_capture import capture_logs_to
from fmriflow.core.run_summary import (
    NodeIdGen, NodeRecord, StageRecord, StudyRunSummary,
)
from fmriflow.core.study_types import StudyResult
from fmriflow.exceptions import ConfigError
from fmriflow.group_orchestrator import _make_run_id  # noqa: F401
from fmriflow.group_orchestrator import latest_run_id
from fmriflow.core.records import _record
from fmriflow.registry import ModuleRegistry

logger = logging.getLogger(__name__)

STUDY_STAGES = [
    'study_collect',
    'groups_fanout',
    'study_analyze',
    'study_report',
]


def _status_from_nodes(nodes: list[NodeRecord]) -> str:
    """Aggregate a stage's per-plugin NodeRecords into a single status.

    ``'failed'`` if every recorded plugin failed, ``'warning'`` if some
    failed and some succeeded, ``'ok'`` otherwise. Empty list maps to
    ``'ok'`` — stages without per-plugin records (``study_collect``,
    ``groups_fanout``) get their status derived elsewhere.
    """
    if not nodes:
        return 'ok'
    statuses = [n.status for n in nodes]
    n_failed = sum(1 for s in statuses if s == 'failed')
    if n_failed == 0:
        return 'warning' if 'warning' in statuses else 'ok'
    if n_failed == len(statuses):
        return 'failed'
    return 'warning'


def _groups_fanout_status(groups: list[GroupResult]) -> str:
    """Derive ``groups_fanout``'s status from the per-group results.

    A :class:`GroupResult` is treated as failed when its
    ``group_summary.status`` is missing or any of its group_stages
    are 'failed' — the same logic that drives the group dashboard.
    """
    if not groups:
        return 'failed'
    n_failed = sum(1 for g in groups if _group_status(g) == 'failed')
    if n_failed == 0:
        return 'ok'
    if n_failed == len(groups):
        return 'failed'
    return 'warning'


def _group_status(group: GroupResult) -> str:
    """Aggregate one group's overall status from its group_summary."""
    summary = group.group_summary
    if summary is None:
        return 'failed'
    stages = getattr(summary, 'stages', None) or getattr(
        summary, 'group_stages', None) or []
    bad = [s for s in stages if getattr(s, 'status', None) == 'failed']
    if bad:
        return 'failed'
    sub_summaries = getattr(summary, 'subject_summaries', None) or []
    if sub_summaries and all(
        (s.get('status') == 'failed' if isinstance(s, dict)
         else getattr(s, 'status', None) == 'failed')
        for s in sub_summaries
    ):
        return 'failed'
    return 'ok'


def _aggregate_study_status(study_stages: list, group_summaries: list) -> str:
    """Derive the top-level study status from stage + group records.

    ``'ok'`` only when every stage is ok and every group ok. ``'failed'``
    when any study stage failed or every group failed. ``'warning'``
    for partial outcomes (an isolated plugin failure, or some groups
    failing while others completed)."""
    stage_statuses = [getattr(s, 'status', 'unknown') for s in study_stages]
    if any(s == 'failed' for s in stage_statuses):
        return 'failed'
    group_statuses = []
    for gs in group_summaries:
        stages = getattr(gs, 'stages', None) or getattr(
            gs, 'group_stages', None) or []
        bad = any(getattr(s, 'status', None) == 'failed' for s in stages)
        group_statuses.append('failed' if bad else 'ok')
    if group_statuses and all(s == 'failed' for s in group_statuses):
        return 'failed'
    has_warn = any(s == 'warning' for s in stage_statuses)
    has_group_fail = any(s == 'failed' for s in group_statuses)
    if has_warn or has_group_fail:
        return 'warning'
    return 'ok'




# ─── group collection ──────────────────────────────────────────

def collect_study_groups(entries, config_path: Path | None = None) -> list[tuple[str, dict]]:
    """Resolve a study's ``groups:`` entries into ``(label, group_config)``.

    Validates:
      - ``groups:`` is a non-empty list of dicts.
      - Every entry has a ``name:`` (study-scope label).
      - Labels are unique within the study.
      - Every entry has a ``config:`` path (inline group bodies
        are deferred to v2).
      - The referenced group YAML loads and has a top-level
        ``group:`` field.
    """
    if not isinstance(entries, list) or not entries:
        raise ConfigError("Study config requires a non-empty 'groups' list")

    seen: set[str] = set()
    out: list[tuple[str, dict]] = []
    errors: list[str] = []
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"groups[{i}]: entry must be a dict")
            continue
        label = entry.get('name')
        if not isinstance(label, str) or not label:
            errors.append(f"groups[{i}]: missing or empty 'name'")
            continue
        if label in seen:
            errors.append(
                f"groups[{i}]: duplicate label '{label}' "
                "(each study-scope group name must be unique)"
            )
            continue
        seen.add(label)

        cfg_path = entry.get('config')
        if not isinstance(cfg_path, str) or not cfg_path:
            errors.append(
                f"groups[{i}] ({label}): missing 'config:' "
                "(inline group bodies are not supported in v1)"
            )
            continue
        p = find_group_config(cfg_path, config_path)
        if p is None:
            tried = ", ".join(str(c) for c in group_config_candidates(cfg_path, config_path))
            errors.append(
                f"groups[{i}] ({label}): config file not found "
                f"at {cfg_path} (searched: {tried})"
            )
            continue
        try:
            with open(p) as f:
                group_cfg = yaml.safe_load(f) or {}
            # Stash where this group YAML actually lives so
            # downstream code (e.g. group_orchestrator.derive_subject_config)
            # could resolve nested paths if it wants to.
            group_cfg.setdefault('_source_path', str(p.resolve()))
        except Exception as exc:
            errors.append(
                f"groups[{i}] ({label}): failed to load YAML: {exc}"
            )
            continue
        if not isinstance(group_cfg.get('group'), str):
            errors.append(
                f"groups[{i}] ({label}): referenced YAML lacks top-level "
                "'group:' — is it actually a group config?"
            )
            continue
        out.append((label, group_cfg))

    if errors:
        raise ConfigError(errors)
    return out


def group_config_candidates(cfg_path: str, config_path: Path | None = None) -> list[Path]:
    """Where to look for a ``groups[i].config`` path.

    An absolute path is taken at face value. A relative path is tried,
    in order, against:
      1. the cwd (literal interpretation),
      2. the study YAML's own directory (the natural place for a
         study to refer to its siblings),
      3. the analysis config root and its ``group/`` subdir
         (where ConfigStore writes duplicates and where users
         typically keep their canonical group YAMLs),
      4. the legacy ``./experiments/`` + ``./experiments/group/``
         tree that the scan-fallback still indexes.
    """
    p = Path(cfg_path)
    if p.is_absolute():
        return [p]
    candidates: list[Path] = [p]
    if config_path is not None:
        candidates.append(Path(config_path).parent / cfg_path)
    try:
        analysis_root = Path(paths.config_dir('analysis'))
        candidates.append(analysis_root / 'group' / cfg_path)
        candidates.append(analysis_root / cfg_path)
        candidates.append(analysis_root / 'study' / cfg_path)
    except Exception:
        # ``paths.config_dir`` may raise in test environments without
        # FMRIFLOW_HOME — fall back to the legacy tree only.
        pass
    candidates.append(Path('./experiments/group') / cfg_path)
    candidates.append(Path('./experiments') / cfg_path)
    return candidates


def find_group_config(cfg_path: str, config_path: Path | None = None) -> Path | None:
    """First existing file from :func:`group_config_candidates`."""
    for cand in group_config_candidates(cfg_path, config_path):
        if cand.is_file():
            return cand
    return None


def __getattr__(name: str):
    """``StudyOrchestrator`` is the graph engine's study runner (imported lazily: the runners import this module)."""
    if name == "StudyOrchestrator":
        from fmriflow.analysis.scope_runners import StudyGraphRunner
        return StudyGraphRunner
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
