"""Pipeline — user-facing API for running experiments."""

from __future__ import annotations

from pathlib import Path

from fmriflow.config.loader import load_config
from fmriflow.context import PipelineContext
from fmriflow.orchestrator import PipelineOrchestrator
from fmriflow.registry import PluginRegistry


class Pipeline:
    """User-facing API for configuring and running pipelines.

    Examples
    --------
    >>> pipeline = Pipeline.from_yaml("experiment.yaml")
    >>> result = pipeline.run()

    >>> pipeline = Pipeline(config={"experiment": "test", "subject": "sub01", ...})
    >>> result = pipeline.run(stages=["features", "preprocess"])
    """

    def __init__(self, config: dict, registry: PluginRegistry | None = None):
        self.config = config
        self.registry = registry or PluginRegistry()
        self.registry.discover()
        self.last_context: PipelineContext | None = None

    @classmethod
    def from_yaml(cls, path: str | Path,
                  registry: PluginRegistry | None = None) -> Pipeline:
        """Create a Pipeline from a YAML config file.

        Parameters
        ----------
        path : str or Path
            Path to experiment YAML config.
        registry : PluginRegistry, optional
            Custom registry. If None, uses default with auto-discovery.

        Returns
        -------
        Pipeline
        """
        config = load_config(path)
        return cls(config, registry=registry)

    def run(self, stages: list[str] | None = None,
            resume_from: str | None = None,
            context: PipelineContext | None = None) -> PipelineContext:
        """Run the pipeline.

        Parameters
        ----------
        stages : list of str, optional
            Specific stages to run. If None, runs all stages.
        resume_from : str, optional
            Stage name to resume from (loads checkpoint).
        context : PipelineContext, optional
            Pre-existing context to continue from.

        Returns
        -------
        PipelineContext
            Context containing all outputs and artifacts.
        """
        orchestrator = PipelineOrchestrator(self.config, self.registry)

        if resume_from is not None:
            context = PipelineContext.from_checkpoint(self.config, resume_from)

        try:
            ctx = orchestrator.run(stages=stages, context=context)
        finally:
            self.last_context = orchestrator.ctx
        return ctx
