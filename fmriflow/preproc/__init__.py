"""fMRI preprocessing module — standalone, decoupled from the analysis pipeline.

Public API:
    PreprocManifest, RunRecord, RunQC  — the contract between preprocessing and analysis
    PreprocConfig, ConfoundsConfig     — configuration dataclasses
    validate_manifest                  — check manifest validity
    run_preprocessing                  — run preprocessing via a backend
    collect_outputs                    — build manifest from existing outputs
    get_backend, list_backends         — backend registry
"""

from fmriflow.preproc.manifest import (
    ConfoundsConfig,
    PreprocConfig,
    PreprocManifest,
    PreprocStatus,
    RunQC,
    RunRecord,
)
from fmriflow.preproc.validation import validate_manifest
from fmriflow.preproc.runner import collect_outputs, run_preprocessing
from fmriflow.preproc.backends import get_backend, list_backends

__all__ = [
    "PreprocManifest",
    "RunRecord",
    "RunQC",
    "PreprocConfig",
    "ConfoundsConfig",
    "PreprocStatus",
    "validate_manifest",
    "run_preprocessing",
    "collect_outputs",
    "get_backend",
    "list_backends",
]
