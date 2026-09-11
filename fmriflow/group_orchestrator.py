"""Group runs: subject configs, run directories and summaries.

The helpers here resolve what a group run does (``derive_subject_config``,
``resolve_subject_list``), find earlier runs (``latest_run_id``) and fold second-pass
records into subject summaries. The runner itself is
:class:`fmriflow.analysis.scope_runners.GroupGraphRunner`; ``GroupOrchestrator``
remains as its name here.
"""

from __future__ import annotations

import copy
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from fmriflow import ui as fui
from fmriflow.config.defaults import DEFAULT_CONFIG
from fmriflow.config.loader import merge_configs, resolve_env_vars
from fmriflow.config.schema import validate_config
from fmriflow.context import PipelineContext
from fmriflow.core import paths
from fmriflow.core.group_types import (
    GroupResult, SubjectResult,
)
from fmriflow.core.log_capture import capture_logs_to
from fmriflow.core.run_summary import (
    GroupRunSummary, NodeIdGen, NodeRecord, RunSummary, StageRecord,
)
from fmriflow.exceptions import ConfigError
from fmriflow.registry import ModuleRegistry

logger = logging.getLogger(__name__)

GROUP_STAGES = [
    'group_collect',
    'group_analyze',
    'subject_second_pass',
    'group_report',
]

# Prefix used in PipelineContext for keys injected by group analyzers
# during the optional second pass.
EXTERNAL_PREFIX = 'external.'


def derive_subject_config(group_config: dict, subject: str,
                          *, output_dir: str | None = None,
                          validate: bool | None = None) -> dict:
    """Resolve the per-subject config that would run for *subject* under
    *group_config*. Mirrors :meth:`GroupOrchestrator._build_subject_configs`
    but is pure (no orchestrator state) so the preview routes and tooling
    can use it without spinning up a real run.

    ``validate`` defaults to True when ``output_dir`` is set (a real
    run is being prepared) and False when ``output_dir`` is None
    (preview mode — the config may legitimately be incomplete and the
    caller just wants to inspect the merged shape). Pass ``True`` /
    ``False`` explicitly to override.
    """
    template = group_config.get('subject_template') or {}
    if not template:
        raise ConfigError(
            "Group config requires 'subject_template' with the shared "
            "subject-scope settings"
        )
    overrides = group_config.get('subject_overrides') or {}

    base = copy.deepcopy(template)
    base['subject'] = subject

    group_intermediates = group_config.get('intermediates')
    group_qa = group_config.get('qa')
    if group_intermediates is not None and 'intermediates' not in base:
        base['intermediates'] = copy.deepcopy(group_intermediates)
    if group_qa is not None and 'qa' not in base:
        base['qa'] = copy.deepcopy(group_qa)

    sub_override = overrides.get(subject) or {}
    merged = merge_configs(base, sub_override)
    merged = merge_configs(DEFAULT_CONFIG, merged)
    merged = resolve_env_vars(merged)

    if output_dir is not None:
        merged.setdefault('reporting', {})['output_dir'] = output_dir

    # Resolve the per-mode default: real runs validate, previews don't.
    if validate is None:
        validate = output_dir is not None

    if validate:
        errors = validate_config(merged)
        if errors:
            raise ConfigError(
                [f"subject '{subject}': {e}" for e in errors])
    return merged


def resolve_subject_list(group_config: dict) -> list[str]:
    """The subject ids a group config runs; ``ConfigError`` when absent or malformed."""
    if 'subjects' in group_config:
        subs = group_config['subjects']
        if not isinstance(subs, list):
            raise ConfigError("'subjects' must be a list")
        return list(subs)
    if 'subjects_from' in group_config:
        # Discovery rule — not implemented in Phase 1.
        raise ConfigError(
            "'subjects_from' discovery rule not implemented yet; "
            "use an explicit 'subjects' list for now"
        )
    raise ConfigError("Group config missing 'subjects' list")




# ─── module helpers ─────────────────────────────────────────────

def latest_run_id(parent: Path) -> str | None:
    """Name of the most recent run directory under *parent*, or ``None``.

    Prefers the ``latest`` symlink the orchestrators maintain; falls back to
    the lexically greatest run directory (run ids are sortable UTC stamps).
    Never creates directories.
    """
    parent = Path(parent)
    if not parent.is_dir():
        return None
    link = parent / 'latest'
    if link.is_symlink():
        target = link.resolve()
        if target.is_dir():
            return target.name
    runs = sorted(
        p.name for p in parent.iterdir()
        if p.is_dir() and not p.is_symlink() and p.name != 'latest'
    )
    return runs[-1] if runs else None


def _merge_second_pass_summary(sr: SubjectResult, ctx: PipelineContext) -> None:
    """Fold a second pass's analyze/report records into the subject summary.

    ``PipelineOrchestrator.run`` replaces ``ctx.run_summary`` with a summary
    holding only the stages it just ran, and nothing re-saved the subject's
    ``run_summary.json``, so the second pass left no record on disk. The
    second-pass records replace the first-pass ones of the same name (the
    second pass re-runs those stages in full) and the file is re-saved.
    """
    second = getattr(ctx, 'run_summary', None)
    first = sr.run_summary
    if second is None or second is first:
        return
    replaced = {rec.name: rec for rec in second.stages}
    for rec in replaced.values():
        rec.detail = f"second pass: {rec.detail}" if rec.detail else "second pass"
    first.stages = [replaced.pop(s.name, s) for s in first.stages] + list(replaced.values())
    first.finished_at = second.finished_at
    first.total_elapsed_s = round(first.total_elapsed_s + second.total_elapsed_s, 3)
    ctx.run_summary = first
    try:
        first.save_json(Path(sr.run_dir) / 'run_summary.json')
    except Exception:
        logger.warning("Failed to re-save run_summary.json for %s after the second pass",
                       sr.subject, exc_info=True)


def _subject_already_succeeded(run_dir: Path) -> bool:
    summary = run_dir / 'run_summary.json'
    if not summary.is_file():
        return False
    try:
        rs = RunSummary.from_json(summary)
    except Exception:
        return False
    if not rs.stages:
        return False
    return all(s.status in ('ok', 'warning', 'skipped') for s in rs.stages)


def _load_subject_result_from_disk(subject: str, scfg: dict,
                                   run_dir: Path) -> SubjectResult:
    rs = RunSummary.from_json(run_dir / 'run_summary.json')
    return SubjectResult(
        subject=subject,
        experiment=scfg.get('experiment', ''),
        run_dir=run_dir,
        run_summary=rs,
        context=None,
    )


def _empty_summary(scfg: dict) -> RunSummary:
    now = datetime.now(timezone.utc).isoformat()
    return RunSummary(
        experiment=scfg.get('experiment', ''),
        subject=scfg.get('subject', ''),
        started_at=now,
        finished_at=now,
        total_elapsed_s=0.0,
        stages=[],
        config_snapshot=copy.deepcopy(scfg),
    )


def _make_run_id() -> str:
    """Path-safe ISO UTC stamp, e.g. ``20260530T193738Z``."""
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def __getattr__(name: str):
    """``GroupOrchestrator`` is the graph engine's group runner (imported lazily: the runners import this module)."""
    if name == "GroupOrchestrator":
        from fmriflow.analysis.scope_runners import GroupGraphRunner
        return GroupGraphRunner
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
