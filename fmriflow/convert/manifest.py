"""ConvertManifest — record of a DICOM-to-BIDS conversion.

The manifest is a JSON file written after heudiconv runs.  It records what
was converted, how, and where the outputs live.  Downstream modules
(preprocessing, analysis) can optionally read it for provenance and
validation.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ── Scanner metadata ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class ScannerInfo:
    """Scanner metadata extracted from DICOM headers."""

    manufacturer: str | None = None
    model: str | None = None
    field_strength: float | None = None
    software_version: str | None = None
    station_name: str | None = None
    institution: str | None = None


# ── Heuristic reference ──────────────────────────────────────────────────

@dataclass(frozen=True)
class HeuristicRef:
    """Reference to the heudiconv heuristic used for conversion."""

    name: str
    path: str
    content_hash: str
    scanner_pattern: str | None = None
    description: str | None = None


# ── Per-run record ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class ConvertRunRecord:
    """Per-run record in the conversion manifest."""

    run_name: str
    task: str
    session: str
    source_series: str
    output_file: str       # relative to bids_dir
    sidecar_file: str      # relative to bids_dir
    n_volumes: int
    modality: str          # "bold", "T1w", "T2w", "dwi", "fmap", etc.
    shape: list[int] = field(default_factory=list)
    tr: float | None = None
    notes: str | None = None


# ── The manifest ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ConvertManifest:
    """Record of a DICOM-to-BIDS conversion.

    Written after a successful heudiconv run.
    Consumed (optionally) by the preprocessing module to locate
    and validate the BIDS dataset.
    """

    # What was converted
    subject: str
    dataset: str
    sessions: list[str]
    runs: list[ConvertRunRecord]

    # How it was converted
    heudiconv_version: str
    heuristic: HeuristicRef | None
    parameters: dict[str, Any]

    # Source
    source_dir: str = ""
    scanner: ScannerInfo | None = None

    # Where it lives
    bids_dir: str = ""
    dataset_description: dict[str, Any] | None = None

    # Validation
    bids_valid: bool | None = None
    bids_errors: list[str] = field(default_factory=list)
    bids_warnings: list[str] = field(default_factory=list)

    # Integrity
    created: str = ""
    pipeline_version: str | None = None
    checksum: str | None = None

    # Schema
    manifest_version: int = 1

    # ── Serialization ────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dict."""
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        """Serialize to a JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def save(self, path: str | Path) -> Path:
        """Write manifest to a JSON file."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_json())
        return p

    # ── Deserialization ──────────────────────────────────────────

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConvertManifest:
        """Build a manifest from a dict (e.g. parsed JSON)."""
        runs = []
        for r in data.pop("runs", []):
            runs.append(ConvertRunRecord(**r))

        heuristic_data = data.pop("heuristic", None)
        heuristic = HeuristicRef(**heuristic_data) if heuristic_data else None

        scanner_data = data.pop("scanner", None)
        scanner = ScannerInfo(**scanner_data) if scanner_data else None

        return cls(runs=runs, heuristic=heuristic, scanner=scanner, **data)

    @classmethod
    def from_json(cls, path: str | Path) -> ConvertManifest:
        """Load a manifest from a JSON file."""
        p = Path(path)
        data = json.loads(p.read_text())
        return cls.from_dict(data)


# ── ConvertConfig ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ConvertConfig:
    """Configuration for a DICOM-to-BIDS conversion via heudiconv.

    ``source_dir`` is kept as a single string for backwards compatibility
    with callers, but accepts multiple whitespace-separated paths or a
    YAML list (see the YAML → dict adapter in ``batch.py``). When more
    than one path is given, all are passed to heudiconv's ``--files``,
    which is variadic. Running T1 and BOLD from different source trees
    in one invocation is the canonical way to avoid heudiconv's
    ``.heudiconv/<sub>/ses-<ses>/`` cache reusing stale filegroup.json
    from an earlier same-(subject, session) job.
    """

    # Source. A single path, or whitespace-separated multiple paths.
    source_dir: str
    subject: str

    # Output
    bids_dir: str

    # Heuristic
    heuristic: str

    # Optional
    sessions: list[str] | None = None
    dataset_name: str | None = None

    # Heudiconv parameters
    grouping: str | None = None
    minmeta: bool = False
    overwrite: bool = True

    # Post-conversion
    validate_bids: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConvertConfig:
        """Build from a dict (e.g. YAML config section)."""
        return cls(**data)


# ── Helpers ──────────────────────────────────────────────────────────────

def now_iso() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()
