"""fMRI preprocessing — one node library, one pipeline model, one runner.

Public API:
    PreprocManifest, RunRecord, RunQC, StepRecord — the contract between preprocessing and analysis
    Pipeline, PipelineRunRequest                  — a pipeline and how to run it
    NodeRegistry, preproc_node                    — the node library
    PipelineRunner                                — run a pipeline as one nipype Workflow
    validate_manifest                             — check manifest validity
"""

from fmriflow.preproc.manifest import (
    ConfoundsConfig,
    PreprocConfig,
    PreprocManifest,
    PreprocStatus,
    RunQC,
    RunRecord,
    StepRecord,
)
from fmriflow.preproc.validation import validate_manifest

__all__ = [
    "PreprocManifest", "RunRecord", "RunQC", "StepRecord",
    "PreprocConfig", "ConfoundsConfig", "PreprocStatus",
    "validate_manifest",
    "Pipeline", "PipelineRunRequest", "NodeRegistry", "preproc_node", "PipelineRunner",
]


def __getattr__(name: str):
    # Lazy: the graph / registry / runner import nipype.
    if name in ("Pipeline", "PipelineRunRequest"):
        from fmriflow.preproc import graph
        return getattr(graph, name)
    if name in ("NodeRegistry", "preproc_node"):
        from fmriflow.preproc import node_registry
        return getattr(node_registry, name)
    if name == "PipelineRunner":
        from fmriflow.preproc.pipeline_runner import PipelineRunner
        return PipelineRunner
    raise AttributeError(name)
