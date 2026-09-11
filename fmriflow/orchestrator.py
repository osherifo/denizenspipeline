"""PipelineOrchestrator: a subject config run on the graph engine.

The stage-by-stage orchestrator was retired once the graph engine reproduced it
on every recorded case. This class keeps its constructor, ``run`` and ``ctx`` for
code that uses them: the config compiles to an analysis graph
(:func:`~fmriflow.analysis.compile_legacy.compile_subject_config`) and runs on
:class:`~fmriflow.analysis.executor.GraphExecutor`. ``run(stages=...)`` and
``run(context=...)`` run only those stages, continuing the context
(:func:`~fmriflow.analysis.executor.run_subject_stages`).
"""

from __future__ import annotations

import logging

from fmriflow.context import PipelineContext
from fmriflow.core.records import _record, _relativize  # noqa: F401  (re-exported)
from fmriflow.core.stages import SUBJECT_STAGES
from fmriflow.exceptions import ConfigError, StageError  # noqa: F401  (re-exported)
from fmriflow.registry import ModuleRegistry

logger = logging.getLogger(__name__)

ALL_STAGES = list(SUBJECT_STAGES)


class PipelineOrchestrator:
    """Runs a subject config, or some of its stages, on the graph engine."""

    def __init__(self, config: dict, registry: ModuleRegistry):
        self.config = config
        self.registry = registry
        self.ctx = PipelineContext(config)

    def run(self, stages: list[str] | None = None, context: PipelineContext | None = None,
            *, write_graph: bool = False) -> PipelineContext:
        """Run every stage, or only ``stages`` (an empty list runs nothing), continuing ``context`` when given.

        ``write_graph`` writes the executed graph to ``graph.json`` in the output directory (full runs only).
        """
        from fmriflow.analysis.catalog import NodeCatalog
        from fmriflow.analysis.compile_legacy import compile_subject_config
        from fmriflow.analysis.executor import GraphExecutor, run_subject_stages

        for stage in stages or []:
            if stage not in ALL_STAGES:
                raise ConfigError(f"Unknown stage: '{stage}'")
        catalog = NodeCatalog(self.registry).discover()
        executor = GraphExecutor(catalog)
        try:
            if stages is None and context is None:
                executor.run(compile_subject_config(self.config), write_graph=write_graph)
            else:
                if context is not None:
                    self.ctx = context
                selected = list(ALL_STAGES) if stages is None else list(stages)
                run_subject_stages(self.config, catalog, selected, self.ctx, executor=executor)
        finally:
            if executor.last_context is not None:
                self.ctx = executor.last_context
        return self.ctx
