"""Batch DICOM-to-BIDS conversion — YAML config parsing and batch dataclasses."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class BatchJobConfig:
    """Configuration for a single job within a batch conversion."""
    subject: str
    source_dir: str
    session: str = ""
    # Per-job overrides (merged on top of shared settings)
    dataset_name: str | None = None
    grouping: str | None = None
    minmeta: bool | None = None
    overwrite: bool | None = None
    validate_bids: bool | None = None


@dataclass
class BatchConfig:
    """Top-level batch conversion configuration."""
    heuristic: str
    bids_dir: str
    jobs: list[BatchJobConfig]
    source_root: str = ""
    max_workers: int = 2
    dataset_name: str = ""
    grouping: str = ""
    minmeta: bool = False
    overwrite: bool = True
    validate_bids: bool = True

    def to_convert_params(self, job: BatchJobConfig) -> dict[str, Any]:
        """Merge shared defaults with per-job overrides into a params dict
        compatible with ConvertManager.start_run / _execute_run."""
        source_dir = job.source_dir
        if self.source_root and not Path(source_dir).is_absolute():
            source_dir = str(Path(self.source_root) / source_dir)

        params: dict[str, Any] = {
            "source_dir": source_dir,
            "subject": job.subject,
            "bids_dir": self.bids_dir,
            "heuristic": self.heuristic,
            "minmeta": job.minmeta if job.minmeta is not None else self.minmeta,
            "overwrite": job.overwrite if job.overwrite is not None else self.overwrite,
            "validate_bids": job.validate_bids if job.validate_bids is not None else self.validate_bids,
        }

        if job.session:
            params["sessions"] = [job.session]

        ds = job.dataset_name if job.dataset_name is not None else (self.dataset_name or None)
        if ds:
            params["dataset_name"] = ds

        grp = job.grouping if job.grouping is not None else (self.grouping or None)
        if grp:
            params["grouping"] = grp

        return params


def parse_batch_yaml(text: str) -> BatchConfig:
    """Parse a YAML batch config string into a BatchConfig."""
    import yaml

    raw = yaml.safe_load(text)
    if not isinstance(raw, dict):
        raise ValueError("Batch YAML must be a mapping at the top level")

    # Support both top-level keys and nested under 'convert_batch'
    data = raw.get("convert_batch", raw)

    jobs_raw = data.get("jobs", [])
    if not jobs_raw:
        raise ValueError("Batch config must contain at least one job under 'jobs'")

    source_root = data.get("source_root", "")

    jobs: list[BatchJobConfig] = []
    for i, j in enumerate(jobs_raw):
        if not isinstance(j, dict):
            raise ValueError(f"Job {i} must be a mapping")
        if "subject" not in j:
            raise ValueError(f"Job {i} missing required field 'subject'")

        source_dir = j.get("source_dir", "")
        if not source_dir:
            raise ValueError(f"Job {i} missing required field 'source_dir'")

        # Accept a YAML list of paths too — heudiconv's --files is
        # variadic, and running multiple DICOM roots in ONE job avoids
        # the .heudiconv/<sub>/ses-<ses>/ cache stomping that happens
        # when two jobs share a (subject, session) pair. Collapse to a
        # whitespace-separated string so downstream code doesn't need
        # to know about list form.
        if isinstance(source_dir, (list, tuple)):
            source_dir = " ".join(str(p) for p in source_dir)

        jobs.append(BatchJobConfig(
            subject=str(j["subject"]),
            source_dir=str(source_dir),
            session=str(j.get("session", "")),
            dataset_name=j.get("dataset_name"),
            grouping=j.get("grouping"),
            minmeta=j.get("minmeta"),
            overwrite=j.get("overwrite"),
            validate_bids=j.get("validate_bids"),
        ))

    heuristic = data.get("heuristic", "")
    if not heuristic:
        raise ValueError("Batch config missing required field 'heuristic'")

    bids_dir = data.get("bids_dir", "")
    if not bids_dir:
        raise ValueError("Batch config missing required field 'bids_dir'")

    return BatchConfig(
        heuristic=str(heuristic),
        bids_dir=str(bids_dir),
        jobs=jobs,
        source_root=str(source_root),
        max_workers=int(data.get("max_workers", 2)),
        dataset_name=str(data.get("dataset_name", "")),
        grouping=str(data.get("grouping", "")),
        minmeta=bool(data.get("minmeta", False)),
        overwrite=bool(data.get("overwrite", True)),
        validate_bids=bool(data.get("validate_bids", True)),
    )


def batch_config_to_dict(config: BatchConfig) -> dict[str, Any]:
    """Serialize a BatchConfig to a dict suitable for JSON / YAML export."""
    return {
        "convert_batch": {
            "heuristic": config.heuristic,
            "bids_dir": config.bids_dir,
            "source_root": config.source_root,
            "max_workers": config.max_workers,
            "dataset_name": config.dataset_name,
            "grouping": config.grouping,
            "minmeta": config.minmeta,
            "overwrite": config.overwrite,
            "validate_bids": config.validate_bids,
            "jobs": [
                {
                    "subject": j.subject,
                    "source_dir": j.source_dir,
                    **({"session": j.session} if j.session else {}),
                }
                for j in config.jobs
            ],
        }
    }


def generate_job_id(job: BatchJobConfig) -> str:
    """Generate a unique job ID from subject + session + short uuid."""
    parts = [job.subject]
    if job.session:
        parts.append(job.session)
    parts.append(uuid.uuid4().hex[:6])
    return "_".join(parts)
