"""StudyOrchestrator — runs M groups, then study-scope analysis and report.

Sits above :class:`fmriflow.group_orchestrator.GroupOrchestrator`. The
group pipeline (collect → analyze → optional second pass → report) is
untouched; this orchestrator fans out groups and reduces across them
the same way GroupOrchestrator fans out subjects.

See ``devdocs/proposals/data-processing/study-analysis.md`` for the
design and the resolved decisions baked in here (in-memory contexts,
unique group labels, default output dir, reference-only groups).
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
from fmriflow.group_orchestrator import GroupOrchestrator, _make_run_id
from fmriflow.orchestrator import _record
from fmriflow.registry import ModuleRegistry

logger = logging.getLogger(__name__)

STUDY_STAGES = [
    'study_collect',
    'groups_fanout',
    'study_analyze',
    'study_report',
]


class StudyOrchestrator:
    """Coordinate a study-scope run across M groups.

    The orchestrator:

    1. **study_collect** — resolves each entry in ``groups:`` to a
       (label, group_config) pair. Validates that labels are unique;
       inline group bodies are not supported in v1 (reference-only).
    2. **groups_fanout** — runs each group via :class:`GroupOrchestrator`.
       Parallel via a thread pool (``parallel.max_workers`` defaults to
       1; groups are GPU-bound). Each group's ``output_dir`` is pinned
       under ``<study_dir>/groups/<label>/`` so the on-disk layout is
       symmetric with the group orchestrator's ``subjects/<subject>/``.
    3. **study_analyze** — runs ``@study_analyzer`` plugins in declared
       order. Each receives the :class:`StudyResult` (including each
       group's in-memory subject contexts) and writes ``study.*`` keys.
       *No-op in Phase 1 — built-in study analyzers ship in Phase 2.*
    4. **study_report** — runs ``@study_reporter`` plugins. Same.
    5. Persists ``study_summary.json`` to the study output directory.

    Like GroupOrchestrator, this also handles its own log capture
    (``study.log``), event emission (``study_*`` events on the
    FMRIFLOW_EVENTS_FILE stream tagged via :func:`ui.event_context`),
    and a ``latest`` symlink alongside the timestamped run dir.
    """

    def __init__(self, study_config: dict, registry: ModuleRegistry,
                 run_id: str | None = None):
        self.config = study_config
        self.registry = registry
        self.study_name = study_config.get('study') or study_config.get('study_name')
        if not self.study_name:
            raise ConfigError("Study config missing 'study' (name) field")
        self.run_id = run_id or study_config.get('run_id') or _make_run_id()
        self.parent_dir, self.study_dir = self._resolve_study_dir()
        self.study: StudyResult = StudyResult(study_name=self.study_name)
        self._stage_records: list[StageRecord] = []

    # ── public API ──────────────────────────────────────────────

    def run(self, resume: bool = False) -> StudyResult:
        run_start = time.time()
        started_at = datetime.now(timezone.utc).isoformat()

        labels = self._labels_safe()
        fui.emit_event({
            'event': 'study_started',
            'study': self.study_name,
            'run_id': self.run_id,
            'groups': labels,
            'n_groups': len(labels),
            'run_dir': str(self.study_dir),
        })

        with capture_logs_to(self.study_dir / 'study.log'):
            logger.info(
                "Study run '%s' (run_id=%s) starting — %d group(s)",
                self.study_name, self.run_id, len(labels),
            )
            try:
                resolved = self._stage('study_collect', self._collect_groups)
                self.study.groups = self._stage(
                    'groups_fanout',
                    lambda: self._fanout_groups(resolved, resume=resume),
                )

                analyzers = self._resolve_study_analyzers()
                if analyzers:
                    self._stage(
                        'study_analyze',
                        lambda nodes: self._run_study_analyzers(analyzers, nodes),
                        capture_nodes=True,
                    )

                reporters = self._resolve_study_reporters()
                if reporters:
                    self._stage(
                        'study_report',
                        lambda nodes: self._run_study_reporters(reporters, nodes),
                        capture_nodes=True,
                    )
            finally:
                finished_at = datetime.now(timezone.utc).isoformat()
                fui.emit_event({
                    'event': 'study_done',
                    'study': self.study_name,
                    'run_id': self.run_id,
                    'elapsed': round(time.time() - run_start, 3),
                })
                self.study.study_summary = StudyRunSummary(
                    study_name=self.study_name,
                    group_labels=[g.study_label or g.group_name
                                  for g in self.study.groups],
                    started_at=started_at,
                    finished_at=finished_at,
                    total_elapsed_s=round(time.time() - run_start, 3),
                    group_summaries=[g.group_summary for g in self.study.groups
                                     if g.group_summary is not None],
                    study_stages=list(self._stage_records),
                    config_snapshot=copy.deepcopy(self.config),
                    run_id=self.run_id,
                )
                try:
                    self.study.study_summary.save_json(
                        self.study_dir / 'study_summary.json')
                except Exception:
                    logger.warning("Failed to save study_summary.json",
                                   exc_info=True)

        return self.study

    # ── helpers: directory layout ───────────────────────────────

    def _resolve_study_dir(self) -> tuple[Path, Path]:
        """Resolve the parent dir + the timestamped run dir.

        ``output_dir`` in the study config (or
        ``$FMRIFLOW_HOME/study_runs/<study_name>/``) is the *parent*;
        the actual run lands in ``<parent>/<run_id>/`` so re-runs
        don't clobber each other. A ``latest`` symlink in the parent
        points at this run.
        """
        out = self.config.get('output_dir')
        parent = Path(out) if out else paths.study_runs_root() / self.study_name
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
            logger.debug("Could not create 'latest' symlink at %s", link,
                         exc_info=True)

    def _group_output_dir(self, label: str) -> Path:
        p = self.study_dir / 'groups' / label
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _labels_safe(self) -> list[str]:
        """List of study-scope labels for logging — never raises."""
        try:
            return [str(e.get('name'))
                    for e in self.config.get('groups') or []
                    if isinstance(e, dict) and e.get('name')]
        except Exception:
            return []

    # ── study_collect ───────────────────────────────────────────

    def _collect_groups(self) -> list[tuple[str, dict]]:
        """Resolve each ``groups:`` entry into ``(label, group_config)``.

        Validates:
          - ``groups:`` is a non-empty list of dicts.
          - Every entry has a ``name:`` (study-scope label).
          - Labels are unique within the study.
          - Every entry has a ``config:`` path (inline group bodies
            are deferred to v2).
          - The referenced group YAML loads and has a top-level
            ``group:`` field.
        """
        entries = self.config.get('groups')
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
            p = Path(cfg_path)
            if not p.is_file():
                errors.append(
                    f"groups[{i}] ({label}): config file not found at {cfg_path}"
                )
                continue
            try:
                with open(p) as f:
                    group_cfg = yaml.safe_load(f) or {}
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

    # ── groups_fanout ───────────────────────────────────────────

    def _fanout_groups(self, resolved: list[tuple[str, dict]],
                       resume: bool = False) -> list[GroupResult]:
        max_workers = (self.config.get('parallel') or {}).get('max_workers', 1)
        results: list[GroupResult | None] = [None] * len(resolved)

        # Study-level ``intermediates:`` and ``qa:`` apply to every group's
        # subjects unless the referenced group YAML overrides them.
        study_intermediates = self.config.get('intermediates')
        study_qa = self.config.get('qa')

        def _slot(idx: int, label: str, group_cfg: dict) -> GroupResult:
            # Pin output_dir under <study_dir>/groups/<label>/ so the
            # GroupOrchestrator's <output_dir>/<run_id>/ ends up at
            # <study_dir>/groups/<label>/<group_run_id>/.
            scfg = copy.deepcopy(group_cfg)
            scfg['output_dir'] = str(self._group_output_dir(label))
            if study_intermediates is not None and 'intermediates' not in scfg:
                scfg['intermediates'] = copy.deepcopy(study_intermediates)
            if study_qa is not None and 'qa' not in scfg:
                scfg['qa'] = copy.deepcopy(study_qa)

            t0 = time.time()
            fui.emit_event({
                'event': 'study_group_start',
                'study': self.study_name,
                'group_label': label,
                'group_name': scfg.get('group') or label,
            })
            status = 'ok'
            try:
                with fui.event_context(study=self.study_name, group_label=label):
                    sub_run_id = f"{self.run_id}__{label}"
                    orch = GroupOrchestrator(scfg, self.registry, run_id=sub_run_id)
                    gr = orch.run(resume=resume)
            except Exception:
                logger.error("Group '%s' failed inside study",
                             label, exc_info=True)
                gr = orch.group if 'orch' in locals() else GroupResult(
                    group_name=scfg.get('group') or label,
                )
                status = 'failed'
            gr.study_label = label
            fui.emit_event({
                'event': 'study_group_done',
                'study': self.study_name,
                'group_label': label,
                'status': status,
                'elapsed': round(time.time() - t0, 3),
            })
            return gr

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_slot, i, label, group_cfg): i
                for i, (label, group_cfg) in enumerate(resolved)
            }
            for fut in futures:
                idx = futures[fut]
                results[idx] = fut.result()

        return [r for r in results if r is not None]

    # ── study_analyze ───────────────────────────────────────────

    def _resolve_study_analyzers(self) -> list[tuple[str, object]]:
        out: list[tuple[str, object]] = []
        for acfg in self.config.get('study_analyze') or []:
            if not (isinstance(acfg, dict) and acfg.get('name')):
                continue
            name = acfg['name']
            out.append((name, self.registry.get_study_analyzer(name)))
        return out

    def _run_study_analyzers(self,
                             analyzers: list[tuple[str, object]],
                             nodes: list[NodeRecord]) -> None:
        idgen = NodeIdGen('study_analyze')
        for name, sa in analyzers:
            with _record(nodes, idgen, 'study_analyzer', name,
                         isolate=True) as rec:
                try:
                    sa.analyze(self.study, self.config)
                    rec.detail = 'ok'
                except Exception as exc:
                    logger.error("Study analyzer '%s' failed: %s",
                                 name, exc, exc_info=True)
                    raise

    # ── study_report ────────────────────────────────────────────

    def _resolve_study_reporters(self) -> list[tuple[str, object]]:
        out: list[tuple[str, object]] = []
        for rcfg in self.config.get('study_report') or []:
            if not (isinstance(rcfg, dict) and rcfg.get('name')):
                continue
            name = rcfg['name']
            out.append((name, self.registry.get_study_reporter(name)))
        return out

    def _run_study_reporters(self,
                             reporters: list[tuple[str, object]],
                             nodes: list[NodeRecord]) -> None:
        report_cfg = dict(self.config)
        report_cfg['output_dir'] = str(self.study_dir)
        idgen = NodeIdGen('study_report')
        from fmriflow.orchestrator import _relativize
        for name, sr in reporters:
            with _record(nodes, idgen, 'study_reporter', name,
                         isolate=True) as rec:
                try:
                    artifacts = sr.report(self.study, report_cfg) or {}
                    self.study.put(f'report.{getattr(sr, "name", name)}',
                                   artifacts)
                    if isinstance(artifacts, dict):
                        rec.outputs = _relativize(
                            [str(v) for v in artifacts.values() if v],
                            str(self.study_dir),
                        )
                        rec.detail = f"{len(artifacts)} artifact(s)"
                except Exception as exc:
                    logger.error("Study reporter '%s' failed: %s",
                                 name, exc, exc_info=True)
                    raise

    # ── stage timing/recording helper ───────────────────────────

    def _stage(self, name: str, fn, *, capture_nodes: bool = False):
        """Time one study stage; optionally collect per-plugin NodeRecords.

        Emits ``study_stage_start`` / ``study_stage_done`` events so
        the dashboard's study-progress view can light up stages.
        """
        t0 = time.time()
        fui.emit_event({
            'event': 'study_stage_start',
            'stage': name,
            'study': self.study_name,
        })
        nodes: list[NodeRecord] = []
        try:
            out = fn(nodes) if capture_nodes else fn()
            elapsed = round(time.time() - t0, 3)
            self._stage_records.append(StageRecord(
                name=name, status='ok',
                elapsed_s=elapsed, detail='',
                nodes=list(nodes),
            ))
            fui.emit_event({
                'event': 'study_stage_done',
                'stage': name,
                'study': self.study_name,
                'elapsed': elapsed,
            })
            return out
        except Exception as e:
            elapsed = round(time.time() - t0, 3)
            self._stage_records.append(StageRecord(
                name=name, status='failed',
                elapsed_s=elapsed, detail=str(e),
                nodes=list(nodes),
            ))
            fui.emit_event({
                'event': 'study_stage_fail',
                'stage': name,
                'study': self.study_name,
                'elapsed': elapsed,
                'error': str(e),
            })
            raise
