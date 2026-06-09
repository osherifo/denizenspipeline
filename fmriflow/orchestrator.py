"""PipelineOrchestrator — coordinates module execution across stages."""

from __future__ import annotations

import copy
import logging
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from fmriflow import ui
from fmriflow import ui as fui
from fmriflow.context import PipelineContext
from fmriflow.core.run_summary import NodeIdGen, NodeRecord, RunSummary, StageRecord
from fmriflow.core.types import (
    FeatureData, ModelResult, PreparedData, ResponseData, StimulusData,
)
from fmriflow.exceptions import ConfigError, StageError
from fmriflow.registry import ModuleRegistry

logger = logging.getLogger(__name__)

ALL_STAGES = ['stimuli', 'responses', 'features', 'prepare', 'model', 'analyze', 'report']


@contextmanager
def _record(
    nodes: list[NodeRecord], idgen: NodeIdGen, kind: str, name: str,
    *, isolate: bool = False,
) -> Iterator[NodeRecord]:
    """Time one plugin invocation and append a NodeRecord on exit.

    ``isolate=True`` swallows the exception so the surrounding stage
    can keep running (used by the analyze + report stages, which the
    existing orchestrator already runs in isolation per plugin).

    Emits ``node_start`` / ``node_done`` / ``node_fail`` events to
    ``$FMRIFLOW_EVENTS_FILE`` so the live in-flight graph viewer can
    light up the specific plugin that's running right now (not just
    the surrounding stage). The events ride the same event_context
    thread-locals as the existing ``stage_*`` events, so they carry
    ``subject`` / ``group`` / ``study`` tags automatically.
    """
    node_id = idgen.make(name)
    rec = NodeRecord(
        id=node_id, kind=kind, name=name,
        status='ok', elapsed_s=0.0,
    )
    t0 = time.time()
    fui.emit_event({
        'event': 'node_start',
        'node_id': node_id, 'kind': kind, 'name': name,
    })
    try:
        yield rec
        elapsed = round(time.time() - t0, 3)
        rec.elapsed_s = elapsed
        nodes.append(rec)
        fui.emit_event({
            'event': 'node_done',
            'node_id': node_id, 'kind': kind, 'name': name,
            'elapsed': elapsed,
            'detail': rec.detail,
        })
    except Exception as exc:
        elapsed = round(time.time() - t0, 3)
        rec.elapsed_s = elapsed
        if rec.status == 'ok':
            rec.status = 'failed'
        if not rec.detail:
            rec.detail = str(exc)
        nodes.append(rec)
        fui.emit_event({
            'event': 'node_fail',
            'node_id': node_id, 'kind': kind, 'name': name,
            'elapsed': elapsed,
            'error': str(exc),
        })
        if not isolate:
            raise


def _relativize(paths: list[str] | None, output_dir: str | None) -> list[str]:
    """Make paths relative to ``output_dir`` where possible.

    Reporters return a ``{logical_name: path}`` dict; ``paths`` here is
    the dict's values. Falls back to the absolute string when the file
    lives outside ``output_dir`` (rare, but happens for shared caches).
    """
    out: list[str] = []
    base = Path(output_dir).resolve() if output_dir else None
    for p in paths or []:
        if not p:
            continue
        try:
            full = Path(str(p)).resolve()
        except Exception:
            out.append(str(p))
            continue
        if base is not None:
            try:
                out.append(str(full.relative_to(base)))
                continue
            except ValueError:
                pass
        out.append(str(full))
    return out


class PipelineOrchestrator:
    """Coordinates module execution across pipeline stages."""

    def __init__(self, config: dict, registry: ModuleRegistry):
        self.config = config
        self.registry = registry
        self.ctx = PipelineContext(config)
        self._reporter_errors: list[tuple[str, Exception]] = []

    def run(self, stages: list[str] | None = None,
            context: PipelineContext | None = None) -> PipelineContext:
        """Run the full pipeline or specific stages.

        Parameters
        ----------
        stages : list of str, optional
            If provided, only run these stages.
        context : PipelineContext, optional
            If provided, use this context (for resuming).

        Returns
        -------
        PipelineContext
            Context with all stage outputs.
        """
        if context is not None:
            self.ctx = context

        stages_to_run = stages or ALL_STAGES

        # Resolve modules
        modules = self._resolve_modules()

        # Validate upfront
        errors = self._validate_all(modules)
        if errors:
            ui.config_error(errors)
            raise ConfigError(errors)

        # Execute stages
        records: list[StageRecord] = []
        run_start = time.time()
        started_at = datetime.now(timezone.utc).isoformat()

        try:
            for stage_name in stages_to_run:
                if stage_name not in ALL_STAGES:
                    raise ConfigError(f"Unknown stage: '{stage_name}'")

                t0 = ui.stage_start(stage_name)
                # Populated by _run_stage so we still have partial info
                # on failure (e.g. which feature extractor blew up).
                nodes: list[NodeRecord] = []
                try:
                    detail = self._run_stage(stage_name, modules, nodes)
                    elapsed = time.time() - t0
                    if stage_name == 'report' and self._reporter_errors:
                        ui.stage_warn(stage_name, t0, detail)
                        status = 'warning'
                    else:
                        ui.stage_done(stage_name, t0, detail)
                        status = 'ok'
                    records.append(StageRecord(
                        name=stage_name, status=status,
                        elapsed_s=round(elapsed, 3), detail=detail,
                        nodes=list(nodes),
                    ))
                except ConfigError:
                    elapsed = time.time() - t0
                    records.append(StageRecord(
                        name=stage_name, status='failed',
                        elapsed_s=round(elapsed, 3), detail='config error',
                        nodes=list(nodes),
                    ))
                    ui.stage_fail(stage_name, t0)
                    raise
                except Exception as e:
                    elapsed = time.time() - t0
                    records.append(StageRecord(
                        name=stage_name, status='failed',
                        elapsed_s=round(elapsed, 3), detail=str(e),
                        nodes=list(nodes),
                    ))
                    ui.stage_fail(stage_name, t0, str(e))
                    raise StageError(stage_name, e) from e

                if self.config.get('checkpoint', False):
                    self.ctx.save_checkpoint(stage_name)
        finally:
            total_elapsed = time.time() - run_start
            cfg = self.config
            self.ctx.run_summary = RunSummary(
                experiment=cfg.get('experiment', ''),
                subject=cfg.get('subject', ''),
                started_at=started_at,
                finished_at=datetime.now(timezone.utc).isoformat(),
                total_elapsed_s=round(total_elapsed, 3),
                stages=records,
                config_snapshot=copy.deepcopy(cfg),
            )

        return self.ctx

    def _resolve_modules(self) -> dict:
        """Map config to concrete module instances."""
        cfg = self.config
        return {
            'stimulus_loader': self.registry.get_stimulus_loader(
                cfg.get('stimulus', {}).get('loader', 'textgrid')),
            'response_loader': self.registry.get_response_loader(
                cfg.get('response', {}).get('loader', 'cloud')),
            'feature_sources': self._resolve_feature_sources(),
            'preparer': self.registry.get_preparer(
                cfg.get('preparation', {}).get('type', 'default')),
            'analyzers': self._resolve_analyzers(),
            'model': self.registry.get_model(
                cfg.get('model', {}).get('type', 'bootstrap_ridge')),
            'reporters': [
                self.registry.get_reporter(fmt)
                for fmt in cfg.get('reporting', {}).get('formats', ['metrics'])
            ],
        }

    def _resolve_feature_sources(self) -> list[tuple[dict, object]]:
        """Resolve each feature's source from config.

        Returns
        -------
        list of (feature_config, source_instance) pairs
        """
        sources = []
        for feat_cfg in self.config.get('features', []):
            source_type = feat_cfg.get('source', 'compute')
            source = self.registry.get_feature_source(source_type)

            if source_type == 'compute':
                extractor_name = feat_cfg.get('extractor', feat_cfg['name'])
                extractor = self.registry.get_feature_extractor(extractor_name)
                source.set_extractor(extractor)

            sources.append((feat_cfg, source))
        return sources

    def _resolve_analyzers(self) -> dict[str, object]:
        """Resolve analyzer modules from config."""
        analyzers: dict[str, object] = {}
        for acfg in self.config.get('analysis', []):
            name = acfg['name']
            if name in analyzers:
                raise ConfigError(
                    f"Duplicate analyzer name '{name}' in 'analysis' configuration; "
                    "analyzer names must be unique."
                )
            analyzers[name] = self.registry.get_analyzer(name)
        return analyzers

    def _validate_all(self, modules: dict) -> list[str]:
        """Run validate_config on all resolved modules."""
        errors = []

        for name in ('stimulus_loader', 'response_loader', 'preparer', 'model'):
            module = modules[name]
            module_errors = module.validate_config(self.config)
            for e in module_errors:
                errors.append(f"{module.name}: {e}")

        for feat_cfg, source in modules['feature_sources']:
            source_errors = source.validate_config(feat_cfg)
            for e in source_errors:
                errors.append(f"feature '{feat_cfg.get('name', '?')}': {e}")

        for aname, analyzer in modules['analyzers'].items():
            analyzer_errors = analyzer.validate_config(self.config)
            for e in analyzer_errors:
                errors.append(f"analyzer '{aname}': {e}")

        for reporter in modules['reporters']:
            reporter_errors = reporter.validate_config(self.config)
            for e in reporter_errors:
                errors.append(f"reporter '{reporter.name}': {e}")

        return errors

    def _output_dir(self) -> str | None:
        rpt = self.config.get('reporting')
        if isinstance(rpt, dict):
            return rpt.get('output_dir')
        return None

    def _run_stage(self, stage_name: str, modules: dict,
                   nodes: list[NodeRecord]) -> str:
        """Execute a single pipeline stage.

        Appends one :class:`NodeRecord` per plugin invocation to
        ``nodes``. Returns a short detail string for the status line.
        """

        if stage_name == 'stimuli':
            loader_name = self.config.get('stimulus', {}).get('loader', 'textgrid')
            idgen = NodeIdGen('stimuli')
            with _record(nodes, idgen, 'stimulus_loader', loader_name) as rec:
                stimuli = modules["stimulus_loader"].load(self.config)
                self.ctx.put('stimuli', stimuli)
                n = len(stimuli.runs)
                rec.detail = f"{n} runs" if n else f"skipped ({loader_name})"
            return rec.detail

        elif stage_name == 'responses':
            loader_name = self.config.get('response', {}).get('loader', 'cloud')
            idgen = NodeIdGen('responses')
            with _record(nodes, idgen, 'response_loader', loader_name) as rec:
                responses = modules["response_loader"].load(self.config)
                self.ctx.put('responses', responses)
                n = len(responses.responses)
                rec.detail = f"{n} runs loaded"
            return rec.detail

        elif stage_name == 'features':
            stimuli = self.ctx.get('stimuli', StimulusData)
            run_names = list(stimuli.runs.keys())

            # Fall back to response run names when stimuli are empty
            # (e.g. stimulus loader is 'skip' for precomputed features)
            if not run_names:
                responses = self.ctx.get('responses', ResponseData)
                run_names = sorted(responses.responses.keys())

            feature_sets = {}
            idgen = NodeIdGen('features')

            for feat_cfg, source in modules['feature_sources']:
                feature_name = feat_cfg['name']
                source_kind = feat_cfg.get('source', 'compute')
                extractor_name = feat_cfg.get('extractor', feature_name)
                # Match the run-graph builder's node-kind rule: a
                # 'compute' feature surfaces the extractor; everything
                # else surfaces the source plugin.
                if source_kind == 'compute':
                    plugin_kind = 'feature_extractor'
                    plugin_name = extractor_name
                else:
                    plugin_kind = 'feature_source'
                    plugin_name = source_kind

                with _record(nodes, idgen, plugin_kind, plugin_name) as rec:
                    if source_kind == 'compute':
                        source.set_stimuli(stimuli)
                    feature_set = source.load(run_names, feat_cfg)
                    feature_sets[feature_name] = feature_set
                    ui.feature_info(
                        feature_name, source_kind,
                        n_runs=len(feature_set.data),
                        n_dims=feature_set.n_dims,
                    )
                    rec.detail = f"{feature_name}: {len(feature_set.data)} runs, {feature_set.n_dims} dims"

            self.ctx.put('features', FeatureData(features=feature_sets))
            return f"{len(feature_sets)} feature(s)"

        elif stage_name == 'prepare':
            responses = self.ctx.get('responses', ResponseData)
            features = self.ctx.get('features', FeatureData)
            prep_cfg = self.config.get('preparation', {}) or {}
            ptype = prep_cfg.get('type', 'default') if isinstance(prep_cfg, dict) else 'default'
            idgen = NodeIdGen('prepare')

            with _record(nodes, idgen, 'preparer', ptype) as rec:
                prepared = modules["preparer"].prepare(
                    responses, features, self.config)
                self.ctx.put('prepared', prepared)
                rec.detail = (f"train={prepared.X_train.shape[0]} "
                              f"test={prepared.X_test.shape[0]}")
            # The preparer's own internal sub-steps (when type=='pipeline')
            # are still rolled into the preparer's NodeRecord — they
            # run as part of one call, not as separate orchestrator
            # invocations. Add a record per declared step so the graph
            # shows them (status mirrors the preparer's outcome since
            # we don't time them individually here).
            for step in (prep_cfg.get('steps') or []) if isinstance(prep_cfg, dict) else []:
                if isinstance(step, dict) and step.get('name'):
                    nodes.append(NodeRecord(
                        id=idgen.make(step['name']),
                        kind='preparation_step',
                        name=step['name'],
                        status=rec.status,
                        elapsed_s=0.0,
                        detail='(timed as part of preparer)',
                    ))
            return rec.detail

        elif stage_name == 'model':
            prepared = self.ctx.get('prepared', PreparedData)
            mtype = (self.config.get('model') or {}).get('type', 'bootstrap_ridge')
            idgen = NodeIdGen('model')
            with _record(nodes, idgen, 'model', mtype) as rec:
                with ui.model_live():
                    result = modules["model"].fit(prepared, self.config)
                self.ctx.put('result', result)
                rec.detail = (f"mean={result.scores.mean():.4f} "
                              f"max={result.scores.max():.4f}")
            return rec.detail

        elif stage_name == 'analyze':
            analysis_cfg = self.config.get('analysis', [])
            if not analysis_cfg:
                return "skipped (none configured)"
            # Isolate each analyzer: a failure in one must not skip the rest
            # of the analyze list nor the report stage downstream.
            n_ok = 0
            failed: list[str] = []
            idgen = NodeIdGen('analyze')
            for acfg in analysis_cfg:
                aname = acfg['name']
                analyzer = modules["analyzers"][aname]
                with _record(nodes, idgen, 'analyzer', aname, isolate=True) as rec:
                    try:
                        analyzer.analyze(self.ctx, self.config)
                        n_ok += 1
                        rec.detail = 'ok'
                    except Exception as e:
                        logger.error("Analyzer '%s' failed: %s",
                                     aname, e, exc_info=True)
                        failed.append(aname)
                        # _record will mark this NodeRecord failed
                        # because the exception propagates through the
                        # with-block (isolate=True swallows it).
                        raise
            if failed:
                return (f"{n_ok}/{len(analysis_cfg)} analyzer(s) ok, "
                        f"failed: {', '.join(failed)}")
            return f"{len(analysis_cfg)} analyzer(s)"

        elif stage_name == 'report':
            result = self.ctx.get('result', ModelResult)
            self._reporter_errors = []
            idgen = NodeIdGen('report')
            output_dir = self._output_dir()
            for reporter in modules['reporters']:
                with _record(nodes, idgen, 'reporter', reporter.name,
                             isolate=True) as rec:
                    try:
                        artifacts = reporter.report(result, self.ctx, self.config)
                        self.ctx.add_artifacts(reporter.name, artifacts)
                        if isinstance(artifacts, dict):
                            rec.outputs = _relativize(
                                list(artifacts.values()), output_dir)
                            rec.detail = f"{len(artifacts)} artifact(s)"
                    except Exception as e:
                        logger.error("Reporter '%s' failed: %s",
                                     reporter.name, e, exc_info=True)
                        self._reporter_errors.append((reporter.name, e))
                        raise
            n = sum(len(v) for v in self.ctx.artifacts.values())
            if self._reporter_errors:
                names = ", ".join(name for name, _ in self._reporter_errors)
                detail = (f"{n} artifact(s) saved, "
                          f"{len(self._reporter_errors)} failed: {names}")
            else:
                detail = f"{n} artifact(s) saved"
            if self._reporter_errors and not self.ctx.artifacts:
                raise StageError('report', self._reporter_errors[0][1])
            return detail

        return ""
