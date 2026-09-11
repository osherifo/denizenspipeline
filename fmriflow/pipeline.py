"""Pipeline — user-facing API for running experiments."""

from __future__ import annotations

import os
from pathlib import Path

from fmriflow.config.loader import load_config
from fmriflow.context import PipelineContext
from fmriflow.orchestrator import ALL_STAGES, ConfigError, PipelineOrchestrator
from fmriflow.registry import ModuleRegistry


class Pipeline:
    """User-facing API for configuring and running pipelines.

    Examples
    --------
    >>> pipeline = Pipeline.from_yaml("experiment.yaml")
    >>> result = pipeline.run()

    >>> pipeline = Pipeline(config={"experiment": "test", "subject": "sub01", ...})
    >>> result = pipeline.run(stages=["features", "preprocess"])
    """

    def __init__(self, config: dict, registry: ModuleRegistry | None = None,
                 engine: str | None = None):
        self.config = config
        self.registry = registry or ModuleRegistry()
        self.registry.discover()
        self.engine = resolve_engine(engine)
        self.last_context: PipelineContext | None = None

    @classmethod
    def from_yaml(cls, path: str | Path,
                  registry: ModuleRegistry | None = None,
                  engine: str | None = None) -> Pipeline:
        """Create a Pipeline from a YAML config file.

        Parameters
        ----------
        path : str or Path
            Path to experiment YAML config.
        registry : ModuleRegistry, optional
            Custom registry. If None, uses default with auto-discovery.

        Returns
        -------
        Pipeline
        """
        config = load_config(path)
        return cls(config, registry=registry, engine=engine)

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
        if self.engine == "graph":
            return self._run_graph(stages, resume_from, context)

        orchestrator = PipelineOrchestrator(self.config, self.registry)

        if resume_from is not None:
            if resume_from not in ALL_STAGES:
                raise ConfigError(
                    f"Unknown stage '{resume_from}' for resume_from "
                    f"(known: {', '.join(ALL_STAGES)})")
            context = PipelineContext.from_checkpoint(self.config, resume_from)
            if stages is None:
                # The checkpoint is written after `resume_from` completes,
                # so continue with the stages that follow it.
                stages = ALL_STAGES[ALL_STAGES.index(resume_from) + 1:]

        try:
            ctx = orchestrator.run(stages=stages, context=context)
        finally:
            self.last_context = orchestrator.ctx
        return ctx

    def _run_graph(self, stages, resume_from, context) -> PipelineContext:
        if stages is not None or resume_from is not None or context is not None:
            raise ConfigError(
                "the graph engine runs the whole pipeline; --stages, --resume-from "
                "and continuing a context need --engine legacy")
        from fmriflow.analysis.catalog import NodeCatalog
        from fmriflow.analysis.executor import GraphExecutor, run_subject_config

        executor = GraphExecutor(NodeCatalog(self.registry).discover())
        try:
            return run_subject_config(self.config, self.registry, write_graph=True, executor=executor)
        finally:
            self.last_context = executor.last_context


ENGINES: tuple[str, ...] = ("legacy", "graph")


def resolve_engine(engine: str | None = None) -> str:
    """The engine to run with: the argument, else ``$FMRIFLOW_ENGINE``, else ``legacy``."""
    value = (engine or os.environ.get("FMRIFLOW_ENGINE") or "legacy").strip().lower()
    if value not in ENGINES:
        raise ConfigError(f"unknown engine {value!r}; expected one of {', '.join(ENGINES)}")
    return value
