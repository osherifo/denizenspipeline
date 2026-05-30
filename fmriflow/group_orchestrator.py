"""GroupOrchestrator — runs N subject pipelines, then group-scope stages.

Sits above :class:`fmriflow.orchestrator.PipelineOrchestrator`. The subject
pipeline (the 7 stages) is untouched; this orchestrator just fans out, then
reduces. See ``devdocs/proposals/data-processing/group-analysis.md`` for the
design.
"""

from __future__ import annotations

import copy
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from fmriflow.config.defaults import DEFAULT_CONFIG
from fmriflow.config.loader import merge_configs, resolve_env_vars
from fmriflow.config.schema import validate_config
from fmriflow.context import PipelineContext
from fmriflow.core import paths
from fmriflow.core.group_types import (
    GroupResult, SubjectResult,
)
from fmriflow.core.log_capture import capture_logs_to
from fmriflow.core.run_summary import GroupRunSummary, RunSummary, StageRecord
from fmriflow.exceptions import ConfigError
from fmriflow.orchestrator import PipelineOrchestrator
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


class GroupOrchestrator:
    """Coordinate a group-scope run across many subjects.

    The orchestrator:

    1. Builds per-subject configs by deep-merging ``subject_template`` with
       each entry in ``subject_overrides`` and pointing ``reporting.output_dir``
       under the group's output directory.
    2. Fans out subject pipelines via a thread pool (preserves in-memory
       contexts for an optional second pass).
    3. Runs group analyzers in declared order, storing artifacts on the
       :class:`GroupResult`.
    4. If any group analyzer's ``produces_subject_artifact`` is True, reruns
       ``analyze + report`` on each subject with the analyzer's bindings
       injected under the ``external.*`` namespace.
    5. Runs group reporters.
    6. Persists ``group_summary.json`` to the group output directory.
    """

    def __init__(self, group_config: dict, registry: ModuleRegistry,
                 run_id: str | None = None):
        self.config = group_config
        self.registry = registry
        self.group_name = group_config.get('group') or group_config.get('group_name')
        if not self.group_name:
            raise ConfigError("Group config missing 'group' (name) field")
        # ISO-ish UTC timestamp, path-safe. One run_id per orchestrator
        # instance, so re-runs land in distinct timestamped subdirs.
        self.run_id = run_id or group_config.get('run_id') or _make_run_id()
        self.parent_dir, self.group_dir = self._resolve_group_dir()
        self.group: GroupResult = GroupResult(group_name=self.group_name)
        self._stage_records: list[StageRecord] = []

    # ── public API ──────────────────────────────────────────────

    def run(self, resume: bool = False) -> GroupResult:
        run_start = time.time()
        started_at = datetime.now(timezone.utc).isoformat()

        # Capture every root-logger record produced during the group run.
        # Reporter warnings (e.g. flatmap skipped on mask mismatch) and
        # subject failures all land in <group_dir>/group.log next to the
        # summary JSON. Per-subject logs are written inside _run_one_subject.
        with capture_logs_to(self.group_dir / 'group.log'):
            logger.info("Group run '%s' (run_id=%s) starting — %d subject(s)",
                        self.group_name, self.run_id,
                        len(self._resolve_subject_list_safe()))
            try:
                subject_configs = self._stage('group_collect',
                                              self._build_subject_configs)
                self.group.subjects = self._stage(
                    'subject_fanout',
                    lambda: self._run_subjects(subject_configs, resume=resume),
                )

                analyzers = self._resolve_group_analyzers()
                if analyzers:
                    self._stage(
                        'group_analyze',
                        lambda: self._run_group_analyzers(analyzers),
                    )

                second_pass = [
                    ga for ga in analyzers
                    if getattr(ga, 'produces_subject_artifact', False)
                ]
                if second_pass:
                    self._stage(
                        'subject_second_pass',
                        lambda: self._rerun_subjects_with_bindings(second_pass),
                    )

                reporters = self._resolve_group_reporters()
                if reporters:
                    self._stage(
                        'group_report',
                        lambda: self._run_group_reporters(reporters),
                    )
            finally:
                finished_at = datetime.now(timezone.utc).isoformat()
                self.group.group_summary = GroupRunSummary(
                    group_name=self.group_name,
                    subjects=[sr.subject for sr in self.group.subjects],
                    started_at=started_at,
                    finished_at=finished_at,
                    total_elapsed_s=round(time.time() - run_start, 3),
                    subject_summaries=[sr.run_summary for sr in self.group.subjects],
                    group_stages=list(self._stage_records),
                    config_snapshot=copy.deepcopy(self.config),
                    run_id=self.run_id,
                )
                try:
                    self.group.group_summary.save_json(
                        self.group_dir / 'group_summary.json')
                except Exception:
                    logger.warning("Failed to save group_summary.json",
                                   exc_info=True)

        return self.group

    # ── helpers: directory layout ───────────────────────────────

    def _resolve_group_dir(self) -> tuple[Path, Path]:
        """Resolve the parent directory and the timestamped run directory.

        ``output_dir`` in the group config (or
        ``$FMRIFLOW_HOME/group_runs/<group_name>/``) is the **parent** — the
        actual run lands in a timestamped subdirectory ``<run_id>/``
        underneath it so re-runs don't clobber each other. A ``latest``
        symlink in the parent points at this run.
        """
        out = self.config.get('output_dir')
        parent = Path(out) if out else paths.group_runs_root() / self.group_name
        parent.mkdir(parents=True, exist_ok=True)
        run_dir = parent / self.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        self._update_latest_symlink(parent, run_dir)
        return parent, run_dir

    @staticmethod
    def _update_latest_symlink(parent: Path, target: Path) -> None:
        link = parent / 'latest'
        try:
            if link.is_symlink() or link.exists():
                link.unlink()
            link.symlink_to(target.name, target_is_directory=True)
        except OSError:
            # Filesystem may not support symlinks (e.g. some network mounts).
            # Not fatal — the run still completes; only the convenience link
            # is missing.
            logger.debug("Could not create 'latest' symlink at %s", link,
                         exc_info=True)

    def _subject_output_dir(self, subject: str) -> Path:
        p = self.group_dir / 'subjects' / subject
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _resolve_subject_list_safe(self) -> list[str]:
        """Like ``_resolve_subject_list`` but returns [] on missing config.

        Used by ``run()`` for an early log message; the strict version
        runs later inside ``_build_subject_configs`` and raises properly.
        """
        try:
            return self._resolve_subject_list()
        except ConfigError:
            return []

    # ── group_collect ───────────────────────────────────────────

    def _build_subject_configs(self) -> list[dict]:
        subjects = self._resolve_subject_list()
        template = self.config.get('subject_template') or {}
        if not template:
            raise ConfigError(
                "Group config requires 'subject_template' with the shared "
                "subject-scope settings"
            )
        overrides = self.config.get('subject_overrides') or {}

        configs = []
        for subject in subjects:
            base = copy.deepcopy(template)
            base['subject'] = subject
            sub_override = overrides.get(subject) or {}
            merged = merge_configs(base, sub_override)

            # Apply package defaults + env-var resolution to mirror what
            # `load_config` does for standalone subject YAMLs.
            merged = merge_configs(DEFAULT_CONFIG, merged)
            merged = resolve_env_vars(merged)

            # Always pin the output dir under the group dir so subject
            # artifacts stay grouped on disk.
            reporting = merged.setdefault('reporting', {})
            reporting['output_dir'] = str(self._subject_output_dir(subject))

            errors = validate_config(merged)
            if errors:
                raise ConfigError(
                    [f"subject '{subject}': {e}" for e in errors])
            configs.append(merged)
        return configs

    def _resolve_subject_list(self) -> list[str]:
        if 'subjects' in self.config:
            subs = self.config['subjects']
            if not isinstance(subs, list):
                raise ConfigError("'subjects' must be a list")
            return list(subs)
        if 'subjects_from' in self.config:
            # Discovery rule — not implemented in Phase 1.
            raise ConfigError(
                "'subjects_from' discovery rule not implemented yet; "
                "use an explicit 'subjects' list for now"
            )
        raise ConfigError("Group config missing 'subjects' list")

    # ── subject fan-out ─────────────────────────────────────────

    def _run_subjects(self, subject_configs: list[dict],
                      resume: bool) -> list[SubjectResult]:
        max_workers = (self.config.get('parallel') or {}).get('max_workers', 4)
        results: list[SubjectResult | None] = [None] * len(subject_configs)

        def _slot(idx: int, scfg: dict) -> SubjectResult:
            subject = scfg['subject']
            run_dir = Path(scfg['reporting']['output_dir'])
            if resume and _subject_already_succeeded(run_dir):
                logger.info("Resume: skipping subject %s (already ok)", subject)
                return _load_subject_result_from_disk(subject, scfg, run_dir)
            return self._run_one_subject(scfg)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_slot, i, scfg): i
                for i, scfg in enumerate(subject_configs)
            }
            for fut in futures:
                idx = futures[fut]
                results[idx] = fut.result()

        return [r for r in results if r is not None]

    def _run_one_subject(self, subject_config: dict) -> SubjectResult:
        run_dir = Path(subject_config['reporting']['output_dir'])
        run_dir.mkdir(parents=True, exist_ok=True)

        # Per-subject pipeline.log. `thread_local=True` ensures messages
        # from other subjects (when max_workers > 1) don't bleed in.
        with capture_logs_to(run_dir / 'pipeline.log', thread_local=True):
            logger.info("Subject %s (group=%s, run_id=%s) starting",
                        subject_config.get('subject'),
                        self.group_name, self.run_id)
            orch = PipelineOrchestrator(subject_config, self.registry)
            ctx: PipelineContext | None = None
            try:
                ctx = orch.run()
            except Exception:
                # Pipeline records the failure in ctx.run_summary inside its
                # try/finally — but ConfigError raised during _validate_all
                # exits BEFORE that try block, so run_summary may not exist.
                ctx = orch.ctx
                logger.error("Subject %s failed",
                             subject_config.get('subject'), exc_info=True)
            # Persist per-subject summary even on failure so resume works.
            rs = getattr(ctx, 'run_summary', None) if ctx is not None else None
            if rs is None:
                rs = _empty_summary(subject_config)
                if ctx is not None:
                    ctx.run_summary = rs
            try:
                rs.save_json(run_dir / 'run_summary.json')
            except Exception:
                logger.warning("Failed to save subject run_summary.json",
                               exc_info=True)
            return SubjectResult(
                subject=subject_config['subject'],
                experiment=subject_config.get('experiment', ''),
                run_dir=run_dir,
                run_summary=rs,
                context=ctx,
            )

    # ── group_analyze ───────────────────────────────────────────

    def _resolve_group_analyzers(self) -> list[object]:
        analyzers = []
        for acfg in self.config.get('group_analyze') or []:
            name = acfg['name']
            analyzers.append(self.registry.get_group_analyzer(name))
        return analyzers

    def _run_group_analyzers(self, analyzers: list[object]) -> None:
        for ga in analyzers:
            ga.analyze(self.group, self.config)

    # ── second pass ─────────────────────────────────────────────

    def _rerun_subjects_with_bindings(self, analyzers: list[object]) -> None:
        bindings: dict[str, object] = {}
        for ga in analyzers:
            sub = ga.subject_bindings(self.group) or {}
            bindings.update(sub)
        if not bindings:
            return

        for sr in list(self.group.subjects):
            ctx = sr.context
            if ctx is None:
                logger.warning(
                    "Skipping second pass for %s: no in-memory context "
                    "(loaded from disk)", sr.subject)
                continue
            for key, value in bindings.items():
                ctx.put(f'{EXTERNAL_PREFIX}{key}', value)
            orch = PipelineOrchestrator(sr.run_summary.config_snapshot,
                                        self.registry)
            try:
                orch.run(stages=['analyze', 'report'], context=ctx)
            except Exception:
                logger.error("Second pass failed for %s", sr.subject,
                             exc_info=True)

    # ── group_report ────────────────────────────────────────────

    def _resolve_group_reporters(self) -> list[object]:
        reporters = []
        for rcfg in self.config.get('group_report') or []:
            name = rcfg['name']
            reporters.append(self.registry.get_group_reporter(name))
        return reporters

    def _run_group_reporters(self, reporters: list[object]) -> None:
        # Reporters use config['output_dir'] to decide where to write.
        # The orchestrator's resolved group_dir is the source of truth, so
        # pin it here in case the original config left output_dir unset.
        report_cfg = dict(self.config)
        report_cfg['output_dir'] = str(self.group_dir)
        for gr in reporters:
            artifacts = gr.report(self.group, report_cfg) or {}
            self.group.put(f'report.{gr.name}', artifacts)

    # ── stage timing/recording helper ───────────────────────────

    def _stage(self, name: str, fn):
        t0 = time.time()
        try:
            out = fn()
            self._stage_records.append(StageRecord(
                name=name, status='ok',
                elapsed_s=round(time.time() - t0, 3), detail='',
            ))
            return out
        except Exception as e:
            self._stage_records.append(StageRecord(
                name=name, status='failed',
                elapsed_s=round(time.time() - t0, 3), detail=str(e),
            ))
            raise


# ─── module helpers ─────────────────────────────────────────────

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
