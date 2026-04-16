"""PipelineOrchestrator — coordinates module execution across stages."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from fmriflow import ui
from fmriflow.context import PipelineContext
from fmriflow.core.run_summary import RunSummary, StageRecord
from fmriflow.core.types import (
    FeatureData, ModelResult, PreparedData, ResponseData, StimulusData,
)
from fmriflow.exceptions import ConfigError, StageError
from fmriflow.registry import ModuleRegistry

logger = logging.getLogger(__name__)

ALL_STAGES = ['stimuli', 'responses', 'features', 'prepare', 'model', 'analyze', 'report']


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
                try:
                    detail = self._run_stage(stage_name, modules)
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
                    ))
                except ConfigError:
                    elapsed = time.time() - t0
                    records.append(StageRecord(
                        name=stage_name, status='failed',
                        elapsed_s=round(elapsed, 3), detail='config error',
                    ))
                    ui.stage_fail(stage_name, t0)
                    raise
                except Exception as e:
                    elapsed = time.time() - t0
                    records.append(StageRecord(
                        name=stage_name, status='failed',
                        elapsed_s=round(elapsed, 3), detail=str(e),
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
                config_snapshot={
                    'model_type': cfg.get('model', {}).get('type', ''),
                    'preparation_type': cfg.get('preparation', {}).get('type', ''),
                    'features': [f.get('name', '') for f in cfg.get('features', [])],
                    'split': cfg.get('split', {}),
                },
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

    def _run_stage(self, stage_name: str, modules: dict) -> str:
        """Execute a single pipeline stage.

        Returns a short detail string for the status line.
        """

        if stage_name == 'stimuli':
            stimuli = modules["stimulus_loader"].load(self.config)
            self.ctx.put('stimuli', stimuli)
            n = len(stimuli.runs)
            loader = self.config.get('stimulus', {}).get('loader', 'textgrid')
            return f"{n} runs" if n else f"skipped ({loader})"

        elif stage_name == 'responses':
            responses = modules["response_loader"].load(self.config)
            self.ctx.put('responses', responses)
            n = len(responses.responses)
            return f"{n} runs loaded"

        elif stage_name == 'features':
            stimuli = self.ctx.get('stimuli', StimulusData)
            run_names = list(stimuli.runs.keys())

            # Fall back to response run names when stimuli are empty
            # (e.g. stimulus loader is 'skip' for precomputed features)
            if not run_names:
                responses = self.ctx.get('responses', ResponseData)
                run_names = sorted(responses.responses.keys())

            feature_sets = {}

            for feat_cfg, source in modules['feature_sources']:
                feature_name = feat_cfg['name']

                if feat_cfg.get('source', 'compute') == 'compute':
                    source.set_stimuli(stimuli)

                feature_set = source.load(run_names, feat_cfg)
                feature_sets[feature_name] = feature_set
                ui.feature_info(
                    feature_name,
                    feat_cfg.get('source', 'compute'),
                    n_runs=len(feature_set.data),
                    n_dims=feature_set.n_dims,
                )

            self.ctx.put('features', FeatureData(features=feature_sets))
            return f"{len(feature_sets)} feature(s)"

        elif stage_name == 'prepare':
            responses = self.ctx.get('responses', ResponseData)
            features = self.ctx.get('features', FeatureData)
            prepared = modules["preparer"].prepare(
                responses, features, self.config)
            self.ctx.put('prepared', prepared)
            return (f"train={prepared.X_train.shape[0]} "
                    f"test={prepared.X_test.shape[0]}")

        elif stage_name == 'model':
            prepared = self.ctx.get('prepared', PreparedData)
            with ui.model_live():
                result = modules["model"].fit(prepared, self.config)
            self.ctx.put('result', result)
            return (f"mean={result.scores.mean():.4f} "
                    f"max={result.scores.max():.4f}")

        elif stage_name == 'analyze':
            analysis_cfg = self.config.get('analysis', [])
            if not analysis_cfg:
                return "skipped (none configured)"
            for acfg in analysis_cfg:
                aname = acfg['name']
                analyzer = modules["analyzers"][aname]
                analyzer.analyze(self.ctx, self.config)
            return f"{len(analysis_cfg)} analyzer(s)"

        elif stage_name == 'report':
            result = self.ctx.get('result', ModelResult)
            self._reporter_errors = []
            for reporter in modules['reporters']:
                try:
                    artifacts = reporter.report(result, self.ctx, self.config)
                    self.ctx.add_artifacts(reporter.name, artifacts)
                except Exception as e:
                    logger.error("Reporter '%s' failed: %s",
                                 reporter.name, e, exc_info=True)
                    self._reporter_errors.append((reporter.name, e))
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
