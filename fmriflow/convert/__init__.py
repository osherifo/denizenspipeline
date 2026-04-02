"""DICOM-to-BIDS conversion module — standalone, decoupled from the
analysis pipeline.

Wraps heudiconv with a heuristic registry and manifest contract.

Public API:
    ConvertManifest, ConvertRunRecord    — the conversion record
    HeuristicRef, ScannerInfo            — heuristic and scanner metadata
    ConvertConfig                        — configuration dataclass
    validate_manifest                    — check manifest validity
    run_conversion                       — run heudiconv conversion
    collect_bids                         — build manifest from existing BIDS
    resolve_heuristic                    — resolve heuristic name or path
    list_heuristics                      — list registered heuristics
"""

from fmriflow.convert.manifest import (
    ConvertConfig,
    ConvertManifest,
    ConvertRunRecord,
    HeuristicRef,
    ScannerInfo,
)
from fmriflow.convert.validation import validate_manifest
from fmriflow.convert.runner import collect_bids, run_conversion
from fmriflow.convert.heuristics import (
    list_heuristics,
    resolve_heuristic,
)

__all__ = [
    "ConvertManifest",
    "ConvertRunRecord",
    "HeuristicRef",
    "ScannerInfo",
    "ConvertConfig",
    "validate_manifest",
    "run_conversion",
    "collect_bids",
    "resolve_heuristic",
    "list_heuristics",
]
