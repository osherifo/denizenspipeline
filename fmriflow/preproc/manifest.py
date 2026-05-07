"""PreprocManifest — contract between preprocessing and analysis pipeline.

The manifest is a JSON file written by the preprocessing backend and read by
the analysis pipeline's response loader.  It describes what was processed,
how, and where the outputs live.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ── Quality metrics per run ──────────────────────────────────────────────

@dataclass(frozen=True)
class RunQC:
    """Quality metrics for a single preprocessing run."""

    mean_fd: float | None = None
    max_fd: float | None = None
    n_high_motion_trs: int | None = None
    tsnr_median: float | None = None
    n_outlier_trs: int | None = None
    notes: str | None = None


# ── Per-run record ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class RunRecord:
    """Per-run record in the manifest."""

    run_name: str
    source_file: str
    output_file: str           # relative to output_dir
    n_trs: int
    shape: list[int]
    n_voxels: int | None = None
    confounds_file: str | None = None
    qc: RunQC | None = None


# ── The manifest ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PreprocManifest:
    """Contract between preprocessing and analysis pipeline.

    Written by the preprocessing backend after a successful run.
    Read by the analysis pipeline's response loader to locate and
    validate preprocessed data.
    """

    # What was processed
    subject: str
    dataset: str
    sessions: list[str]
    runs: list[RunRecord]

    # How it was processed
    backend: str
    backend_version: str
    parameters: dict[str, Any]
    space: str
    resolution: str | None = None
    confounds_applied: list[str] = field(default_factory=list)
    additional_steps: list[str] = field(default_factory=list)

    # Where it lives
    output_dir: str = ""
    output_format: str = "nifti"
    file_pattern: str = ""

    # Integrity
    created: str = ""
    pipeline_version: str | None = None
    checksum: str | None = None

    # FreeSurfer outputs (location of SUBJECTS_DIR if backend produced one)
    freesurfer_subjects_dir: str | None = None

    # Post-step outputs
    autoflatten: dict[str, Any] | None = None

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
    def from_dict(cls, data: dict[str, Any]) -> PreprocManifest:
        """Build a manifest from a dict (e.g. parsed JSON)."""
        runs = []
        for r in data.get("runs", []):
            qc_data = r.pop("qc", None) if isinstance(r, dict) else None
            qc = RunQC(**qc_data) if qc_data else None
            runs.append(RunRecord(**{**r, "qc": qc}))

        # Remove 'runs' from data before passing to constructor
        data = {k: v for k, v in data.items() if k != "runs"}
        return cls(runs=runs, **data)

    @classmethod
    def from_json(cls, path: str | Path) -> PreprocManifest:
        """Load a manifest from a JSON file."""
        p = Path(path)
        data = json.loads(p.read_text())
        return cls.from_dict(data)


# ── PreprocConfig ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ConfoundsConfig:
    """Configuration for confound regression."""

    strategy: str                        # "motion_24", "acompcor", "ica_aroma", "custom"
    columns: list[str] | None = None     # explicit confound column names (for "custom")
    high_pass: float | None = None       # high-pass filter cutoff in Hz
    low_pass: float | None = None        # low-pass filter cutoff in Hz
    fd_threshold: float | None = None    # scrub TRs with FD above this
    standardize: bool = True             # z-score confounds before regression


@dataclass(frozen=True)
class PreprocConfig:
    """Configuration for a preprocessing run."""

    # Input
    subject: str
    backend: str                         # "fmriprep", "nipype", "custom", "bids_app"
    output_dir: str
    bids_dir: str | None = None
    raw_dir: str | None = None
    sessions: list[str] | None = None
    task: str | None = None

    # Output
    work_dir: str | None = None

    # Backend-specific
    backend_params: dict[str, Any] = field(default_factory=dict)

    # Run mapping
    run_map: dict[str, str] | None = None

    # Post-processing
    confounds: ConfoundsConfig | None = None

    # Post-steps
    post_steps: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PreprocConfig:
        """Build from a dict (e.g. YAML config section)."""
        confounds_data = data.pop("confounds", None)
        confounds = ConfoundsConfig(**confounds_data) if confounds_data else None
        post_steps = data.pop("post_steps", None)
        return cls(confounds=confounds, post_steps=post_steps, **data)


# ── PreprocStatus ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PreprocStatus:
    """Status of a preprocessing run."""

    status: str   # "pending", "running", "completed", "failed"
    detail: str = ""
    progress: float | None = None  # 0.0 to 1.0


# ── Helpers ──────────────────────────────────────────────────────────────

def now_iso() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()
