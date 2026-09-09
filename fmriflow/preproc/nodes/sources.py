"""Source nodes — where files enter a pipeline.

A source has no input ports. Its ``run()`` resolves files from the run
request (via ``$inputs.*`` bindings) and emits them as outputs so
downstream nodes can connect to them like any other port.

- ``bids_source``         a subject's raw BIDS files (T1w / BOLD) from ``bids_dir``
- ``manifest_source``     one run's preprocessed BOLD (+ confounds) from an
                          existing ``preproc_manifest.json``
- ``derivatives_source``  glob a derivatives dir for preprocessed BOLD files
                          (the old ``passthrough`` bootstrap)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fmriflow.preproc.node_registry import preproc_node

logger = logging.getLogger(__name__)


def _subject_label(subject: str) -> str:
    return subject if subject.startswith("sub-") else f"sub-{subject}"


@preproc_node("bids_source", kind="source")
class BidsSource:
    """Emit a subject's raw BIDS anatomical and functional files."""

    name = "bids_source"
    version = "0.1.0"
    description = "A subject's raw BIDS T1w and BOLD files."
    INPUTS = {
        "bids_dir": {"kind": "dir", "required": True, "description": "BIDS root"},
        "subject": {"kind": "str", "required": True, "description": "subject label"},
    }
    OUTPUTS = {
        "t1w": {"kind": "nifti", "description": "first T1w image"},
        "bold": {"kind": "nifti", "description": "all BOLD runs (list)"},
        "subject_dir": {"kind": "dir", "description": "the sub-<label>/ directory"},
    }
    PARAM_SCHEMA: dict[str, Any] = {
        "task": {"type": "str", "default": "", "description": "Only BOLD runs of this task."},
        "session": {"type": "str", "default": "", "description": "Only this session."},
    }
    REQUIRED_PYTHON: list[str] = []
    REQUIRED_TOOLS: list[str] = []
    REQUIRED_ENV: list[str] = []
    CONTAINER: str | None = None

    def run(self, inputs: dict[str, Any], out_dir: Path, params: dict[str, Any]) -> dict[str, Any]:
        bids_dir = Path(inputs["bids_dir"])
        subject_dir = bids_dir / _subject_label(str(inputs["subject"]))
        if not subject_dir.is_dir():
            raise FileNotFoundError(f"bids_source: no subject directory at {subject_dir}")
        session = str(params.get("session") or "")
        roots = [subject_dir / f"ses-{session}"] if session else [subject_dir]
        task = str(params.get("task") or "")
        t1w = sorted(p for r in roots for p in r.glob("anat/*_T1w.nii*"))
        bold = sorted(
            p for r in roots for p in r.glob("func/*_bold.nii*")
            if not task or f"task-{task}_" in p.name
        )
        out: dict[str, Any] = {"subject_dir": subject_dir, "bold": bold}
        if t1w:
            out["t1w"] = t1w[0]
        return out


@preproc_node("manifest_source", kind="source")
class ManifestSource:
    """Emit one run's preprocessed BOLD (+ confounds) from a preproc manifest."""

    name = "manifest_source"
    version = "0.1.0"
    description = "A run's preprocessed BOLD and confounds from an existing preproc_manifest.json."
    INPUTS = {
        "manifest": {"kind": "file", "required": True, "description": "preproc_manifest.json"},
    }
    OUTPUTS = {
        "bold": {"kind": "nifti", "description": "preprocessed BOLD for run_name"},
        "confounds": {"kind": "tsv", "description": "confounds TSV for run_name"},
    }
    PARAM_SCHEMA: dict[str, Any] = {
        "run_name": {
            "type": "str", "default": "",
            "description": "run_name from the manifest's runs[]; empty = first run.",
        },
    }
    REQUIRED_PYTHON: list[str] = []
    REQUIRED_TOOLS: list[str] = []
    REQUIRED_ENV: list[str] = []
    CONTAINER: str | None = None

    def run(self, inputs: dict[str, Any], out_dir: Path, params: dict[str, Any]) -> dict[str, Any]:
        from fmriflow.preproc.manifest import PreprocManifest

        manifest_path = Path(inputs["manifest"])
        manifest = PreprocManifest.from_dict(json.loads(manifest_path.read_text()))
        if not manifest.runs:
            raise ValueError(f"manifest_source: {manifest_path} has no runs")
        run_name = str(params.get("run_name") or "")
        run = next((r for r in manifest.runs if r.run_name == run_name), None) if run_name else manifest.runs[0]
        if run is None:
            names = ", ".join(r.run_name for r in manifest.runs)
            raise KeyError(f"manifest_source: run {run_name!r} not in manifest (have: {names})")
        base = Path(manifest.output_dir)

        def _abs(p: str | None) -> Path | None:
            if not p:
                return None
            path = Path(p)
            return path if path.is_absolute() else base / path

        out: dict[str, Any] = {}
        bold = _abs(run.output_file)
        if bold is not None:
            out["bold"] = bold
        conf = _abs(run.confounds_file)
        if conf is not None:
            out["confounds"] = conf
        return out


@preproc_node("derivatives_source", kind="source")
class DerivativesSource:
    """Glob an existing derivatives directory for preprocessed BOLD files.

    The successor of the ``passthrough`` bootstrap: data preprocessed
    elsewhere enters the graph here, and transforms can follow.
    """

    name = "derivatives_source"
    version = "0.1.0"
    description = "Preprocessed BOLD files found by glob in an existing derivatives dir."
    INPUTS = {
        "derivatives_dir": {"kind": "dir", "required": True, "description": "derivatives root"},
        "subject": {"kind": "str", "required": False, "description": "restrict to sub-<label>/"},
    }
    OUTPUTS = {
        "bold": {"kind": "nifti", "description": "matched BOLD files (list)"},
        "confounds": {"kind": "tsv", "description": "matching confounds TSVs (list)"},
    }
    PARAM_SCHEMA: dict[str, Any] = {
        "file_pattern": {
            "type": "str", "default": "*_desc-preproc_bold.nii.gz",
            "description": "Glob (recursive) selecting preprocessed BOLD files.",
        },
        "confounds_pattern": {
            "type": "str", "default": "*_desc-confounds_timeseries.tsv",
            "description": "Glob (recursive) selecting confounds TSVs; empty to skip.",
        },
    }
    REQUIRED_PYTHON: list[str] = []
    REQUIRED_TOOLS: list[str] = []
    REQUIRED_ENV: list[str] = []
    CONTAINER: str | None = None

    def run(self, inputs: dict[str, Any], out_dir: Path, params: dict[str, Any]) -> dict[str, Any]:
        root = Path(inputs["derivatives_dir"])
        subject = inputs.get("subject")
        if subject:
            candidate = root / _subject_label(str(subject))
            if candidate.is_dir():
                root = candidate
        if not root.is_dir():
            raise FileNotFoundError(f"derivatives_source: {root} is not a directory")
        pattern = str(params.get("file_pattern") or "*_desc-preproc_bold.nii.gz")
        bold = sorted(root.rglob(pattern))
        if not bold:
            logger.warning("derivatives_source: no files match %s under %s", pattern, root)
        out: dict[str, Any] = {"bold": bold}
        cpat = str(params.get("confounds_pattern") or "")
        if cpat:
            out["confounds"] = sorted(root.rglob(cpat))
        return out
