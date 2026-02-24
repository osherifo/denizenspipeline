"""PipelineOrchestrator — coordinates plugin execution across stages."""

from __future__ import annotations

import logging

from denizenspipeline.context import PipelineContext
from denizenspipeline.core.types import (
    FeatureData, ModelResult, PreparedData, ResponseData, StimulusData,
)
from denizenspipeline.exceptions import ConfigError, StageError
from denizenspipeline.registry import PluginRegistry

logger = logging.getLogger(__name__)

ALL_STAGES = ['stimuli', 'responses', 'features', 'preprocess', 'model', 'report']


class PipelineOrchestrator:
    """Coordinates plugin execution across pipeline stages."""

    def __init__(self, config: dict, registry: PluginRegistry):
        self.config = config
        self.registry = registry
        self.ctx = PipelineContext(config)

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

        # Resolve plugins
        plugins = self._resolve_plugins()

        # Validate upfront
        errors = self._validate_all(plugins)
        if errors:
            raise ConfigError(errors)

        # Execute stages
        for stage_name in stages_to_run:
            if stage_name not in ALL_STAGES:
                raise ConfigError(f"Unknown stage: '{stage_name}'")
            logger.info(f"Running stage: {stage_name}")
            try:
                self._run_stage(stage_name, plugins)
            except ConfigError:
                raise
            except Exception as e:
                raise StageError(stage_name, e) from e

            if self.config.get('checkpoint', False):
                self.ctx.save_checkpoint(stage_name)

        return self.ctx

    def _resolve_plugins(self) -> dict:
        """Map config to concrete plugin instances."""
        cfg = self.config
        return {
            'stimulus_loader': self.registry.get_stimulus_loader(
                cfg.get('stimulus', {}).get('loader', 'textgrid')),
            'response_loader': self.registry.get_response_loader(
                cfg.get('response', {}).get('loader', 'cloud')),
            'feature_sources': self._resolve_feature_sources(),
            'preprocessor': self.registry.get_preprocessor(
                cfg.get('preprocessing', {}).get('type', 'default')),
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

    def _validate_all(self, plugins: dict) -> list[str]:
        """Run validate_config on all resolved plugins."""
        errors = []

        for name in ('stimulus_loader', 'response_loader', 'preprocessor', 'model'):
            plugin = plugins[name]
            plugin_errors = plugin.validate_config(self.config)
            for e in plugin_errors:
                errors.append(f"{plugin.name}: {e}")

        for feat_cfg, source in plugins['feature_sources']:
            source_errors = source.validate_config(feat_cfg)
            for e in source_errors:
                errors.append(f"feature '{feat_cfg.get('name', '?')}': {e}")

        for reporter in plugins['reporters']:
            reporter_errors = reporter.validate_config(self.config)
            for e in reporter_errors:
                errors.append(f"reporter '{reporter.name}': {e}")

        return errors

    def _run_stage(self, stage_name: str, plugins: dict) -> None:
        """Execute a single pipeline stage."""

        if stage_name == 'stimuli':
            stimuli = plugins['stimulus_loader'].load(self.config)
            self.ctx.put('stimuli', stimuli)

        elif stage_name == 'responses':
            responses = plugins['response_loader'].load(self.config)
            self.ctx.put('responses', responses)

        elif stage_name == 'features':
            stimuli = self.ctx.get('stimuli', StimulusData)
            run_names = list(stimuli.runs.keys())
            feature_sets = {}

            for feat_cfg, source in plugins['feature_sources']:
                feature_name = feat_cfg['name']
                logger.info(
                    f"  Loading feature '{feature_name}' "
                    f"(source: {feat_cfg.get('source', 'compute')})")

                if feat_cfg.get('source', 'compute') == 'compute':
                    source.set_stimuli(stimuli)

                feature_set = source.load(run_names, feat_cfg)
                feature_sets[feature_name] = feature_set

            self.ctx.put('features', FeatureData(features=feature_sets))

        elif stage_name == 'preprocess':
            responses = self.ctx.get('responses', ResponseData)
            features = self.ctx.get('features', FeatureData)
            prepared = plugins['preprocessor'].prepare(
                responses, features, self.config)
            self.ctx.put('prepared', prepared)

        elif stage_name == 'model':
            prepared = self.ctx.get('prepared', PreparedData)
            result = plugins['model'].fit(prepared, self.config)
            self.ctx.put('result', result)

        elif stage_name == 'report':
            result = self.ctx.get('result', ModelResult)
            for reporter in plugins['reporters']:
                artifacts = reporter.report(result, self.ctx, self.config)
                self.ctx.add_artifacts(reporter.name, artifacts)
