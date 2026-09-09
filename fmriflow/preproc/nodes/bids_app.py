"""Any BIDS-App as a pipeline node (docker / apptainer / bare)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fmriflow.preproc.container import (
    VALID_CONTAINER_TYPES,
    container_prefix,
    resolve_container_type,
    guest_paths,
    runtime_available,
)
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
        "work_dir": {"kind": "dir", "required": False, "description": "bound at /work when set"},
    }
    OUTPUTS = {
        "derivatives_dir": {"kind": "dir", "description": "app output root"},
        "files": {"kind": "nifti", "description": "outputs matching file_pattern (list)"},
        "manifest": {"kind": "json", "description": "preproc_manifest.json for this run"},
    }
    PARAM_SCHEMA: dict[str, Any] = {
        "container": {"type": "str", "default": "", "required": True,
                      "description": "Image (docker tag / .sif / docker:// URI) or, for bare, the executable."},
        "container_type": {"type": "str", "default": "docker", "enum": list(VALID_CONTAINER_TYPES)},
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
        container = str(params.get("container") or "")
        ctype = resolve_container_type(str(params.get("container_type") or "auto"), binary=str(params.get("container") or ""))
        if not container:
            errors.append("container is required (image, .sif path, or executable for bare)")
        if ctype not in VALID_CONTAINER_TYPES:
            errors.append(f"container_type must be one of {VALID_CONTAINER_TYPES}")
        if not inputs.get("bids_dir") or not Path(inputs["bids_dir"]).is_dir():
            errors.append(f"BIDS directory not found: {inputs.get('bids_dir')}")
        if container and ctype != "bare" and not runtime_available(container, ctype):
            errors.append(f"cannot launch container {container!r} as {ctype}: runtime not available")
        return errors

    def build_command(self, inputs: dict[str, Any], params: dict[str, Any], out_dir: Path) -> list[str]:
        container = str(params["container"])
        ctype = resolve_container_type(str(params.get("container_type") or "auto"), binary=str(params.get("container") or ""))
        bids_dir = str(inputs["bids_dir"])
        output_dir, work_dir = self._dirs(inputs, out_dir)
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        if work_dir:
            Path(work_dir).mkdir(parents=True, exist_ok=True)
        if ctype == "bare":
            cmd = [container]
        else:
            cmd = container_prefix(container, ctype, bids_dir=bids_dir, output_dir=output_dir, work_dir=work_dir)
        g_bids, g_out, _ = guest_paths(ctype, bids_dir=bids_dir, output_dir=output_dir, work_dir=work_dir)
        cmd += [g_bids, g_out, "participant", "--participant-label", str(inputs["subject"])]
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
