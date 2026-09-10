"""Any BIDS-App installed on PATH as a pipeline node (bare execution)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import shutil
from fmriflow.preproc.node_registry import preproc_node

logger = logging.getLogger(__name__)


@preproc_node("bids_app", kind="container_app")
class BidsAppNode:
    """Run a generic BIDS-App (``<app> <bids> <out> participant --participant-label <sub>``)."""

    name = "bids_app"
    version = "0.2.0"
    description = "Any BIDS-App container or executable, run at the participant level."
    INNER_NIPYPE_LOG = False
    FINGERPRINT_INPUTS = ["bids_dir"]
    REQUIRED_PYTHON: list[str] = []
    REQUIRED_TOOLS: list[str] = []
    REQUIRED_ENV: list[str] = []
    CONTAINER: str | None = None

    INPUTS = {
        "bids_dir": {"kind": "dir", "required": True, "exists": True, "description": "BIDS root"},
        "subject": {"kind": "str", "required": True, "description": "participant label (no sub-)"},
        "output_dir": {"kind": "dir", "required": False, "description": "app output root (default: node dir/derivatives)"},
        "work_dir": {"kind": "dir", "required": False, "description": "passed as -w when set"},
    }
    OUTPUTS = {
        "derivatives_dir": {"kind": "dir", "description": "app output root"},
        "files": {"kind": "nifti", "description": "outputs matching file_pattern (list)"},
        "manifest": {"kind": "json", "description": "preproc_manifest.json for this run"},
    }
    PARAM_SCHEMA: dict[str, Any] = {
        "command": {"type": "str", "default": "", "required": True,
                    "description": "The BIDS-App executable (name on PATH or absolute path)."},
        "extra_args": {"type": "list[string]", "default": [], "description": "Extra CLI arguments."},
        "file_pattern": {"type": "str", "default": "*_desc-preproc_bold.nii.gz",
                         "description": "Glob (recursive) selecting the app's output files."},
        "space": {"type": "str", "default": "native", "description": "Output space label for the manifest."},
    }

    @staticmethod
    def _dirs(inputs: dict[str, Any], out_dir: Path) -> tuple[str, str | None]:
        output_dir = str(inputs.get("output_dir") or out_dir / "derivatives")
        work_dir = str(inputs["work_dir"]) if inputs.get("work_dir") else None
        return output_dir, work_dir

    def validate(self, inputs: dict[str, Any], params: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        command = self._command(params)
        if not command:
            errors.append("command is required (the BIDS-App executable)")
        elif not (Path(command).is_file() or shutil.which(command)):
            errors.append(f"command not found on PATH: {command}")
        if not inputs.get("bids_dir") or not Path(inputs["bids_dir"]).is_dir():
            errors.append(f"BIDS directory not found: {inputs.get('bids_dir')}")
        return errors

    @staticmethod
    def _command(params: dict[str, Any]) -> str:
        # `container` is the pre-bare-only spelling still found in older saved pipelines.
        return str(params.get("command") or params.get("container") or "")

    def build_command(self, inputs: dict[str, Any], params: dict[str, Any], out_dir: Path) -> list[str]:
        bids_dir = str(inputs["bids_dir"])
        output_dir, work_dir = self._dirs(inputs, out_dir)
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        if work_dir:
            Path(work_dir).mkdir(parents=True, exist_ok=True)
        cmd = [self._command(params), bids_dir, output_dir, "participant", "--participant-label", str(inputs["subject"])]
        if work_dir:
            cmd += ["-w", work_dir]
        cmd += [str(a) for a in (params.get("extra_args") or [])]
        return cmd

    def collect(self, inputs: dict[str, Any], params: dict[str, Any], out_dir: Path) -> dict[str, Any]:
        manifest = self.to_manifest(inputs, params, out_dir)
        output_dir, _ = self._dirs(inputs, out_dir)
        base = Path(output_dir)
        manifest_path = Path(out_dir) / "preproc_manifest.json"
        manifest_path.write_text(json.dumps(manifest.to_dict(), indent=2))
        return {
            "derivatives_dir": base,
            "files": [base / r.output_file for r in manifest.runs],
            "manifest": manifest_path,
        }

    def to_manifest(self, inputs: dict[str, Any], params: dict[str, Any], out_dir: Path):
        from fmriflow.preproc.backends.bids_app import BidsAppBackend
        from fmriflow.preproc.manifest import PreprocConfig

        output_dir, work_dir = self._dirs(inputs, out_dir)
        config = PreprocConfig(
            subject=str(inputs["subject"]),
            backend="bids_app",
            output_dir=output_dir,
            bids_dir=str(inputs.get("bids_dir") or ""),
            work_dir=work_dir,
            backend_params=dict(params),
        )
        return BidsAppBackend().collect(config)
