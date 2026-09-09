"""A shell command template as a pipeline node."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fmriflow.preproc.node_registry import preproc_node

logger = logging.getLogger(__name__)

TEMPLATE_KEYS = ("subject", "session", "input_dir", "output_dir", "node_dir")


@preproc_node("custom_shell", kind="container_app")
class CustomShellNode:
    """Run a shell command template and collect its outputs by glob.

    The template may use ``{subject}``, ``{session}``, ``{input_dir}``,
    ``{output_dir}`` and ``{node_dir}``.
    """

    name = "custom_shell"
    version = "0.2.0"
    description = "Run a shell command template; outputs collected by glob."
    INNER_NIPYPE_LOG = False
    FINGERPRINT_INPUTS = ["input_dir"]
    REQUIRED_PYTHON: list[str] = []
    REQUIRED_TOOLS: list[str] = []
    REQUIRED_ENV: list[str] = []
    CONTAINER: str | None = None

    INPUTS = {
        "input_dir": {"kind": "dir", "required": False, "description": "{input_dir} in the template"},
        "subject": {"kind": "str", "required": False, "description": "{subject} in the template"},
        "session": {"kind": "str", "required": False, "description": "{session} in the template"},
        "output_dir": {"kind": "dir", "required": False, "description": "{output_dir} (default: node dir/out)"},
    }
    OUTPUTS = {
        "output_dir": {"kind": "dir", "description": "where the command wrote"},
        "files": {"kind": "file", "description": "outputs matching file_pattern (list)"},
        "manifest": {"kind": "json", "description": "preproc_manifest.json for this run"},
    }
    PARAM_SCHEMA: dict[str, Any] = {
        "command": {"type": "str", "default": "", "required": True,
                    "description": "Shell command template, e.g. 'mytool {input_dir} {output_dir} --sub {subject}'."},
        "file_pattern": {"type": "str", "default": "*.nii.gz", "description": "Glob (recursive) for output files."},
        "version": {"type": "str", "default": "unknown", "description": "Version label for the manifest."},
        "space": {"type": "str", "default": "native"},
        "output_format": {"type": "str", "default": "nifti"},
    }

    @staticmethod
    def _output_dir(inputs: dict[str, Any], out_dir: Path) -> str:
        return str(inputs.get("output_dir") or out_dir / "out")

    def validate(self, inputs: dict[str, Any], params: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        if not str(params.get("command") or "").strip():
            errors.append("command template is required")
        try:
            self.render(inputs, params, Path("/tmp"))
        except KeyError as e:
            errors.append(f"unknown template placeholder {e.args[0]!r}; allowed: {', '.join(TEMPLATE_KEYS)}")
        return errors

    def render(self, inputs: dict[str, Any], params: dict[str, Any], out_dir: Path) -> str:
        return str(params.get("command") or "").format(
            subject=str(inputs.get("subject") or ""),
            session=str(inputs.get("session") or ""),
            input_dir=str(inputs.get("input_dir") or ""),
            output_dir=self._output_dir(inputs, out_dir),
            node_dir=str(out_dir),
        )

    def build_command(self, inputs: dict[str, Any], params: dict[str, Any], out_dir: Path) -> str:
        Path(self._output_dir(inputs, out_dir)).mkdir(parents=True, exist_ok=True)
        return self.render(inputs, params, out_dir)

    def collect(self, inputs: dict[str, Any], params: dict[str, Any], out_dir: Path) -> dict[str, Any]:
        manifest = self.to_manifest(inputs, params, out_dir)
        base = Path(self._output_dir(inputs, out_dir))
        manifest_path = Path(out_dir) / "preproc_manifest.json"
        manifest_path.write_text(json.dumps(manifest.to_dict(), indent=2))
        return {
            "output_dir": base,
            "files": [base / r.output_file for r in manifest.runs],
            "manifest": manifest_path,
        }

    def to_manifest(self, inputs: dict[str, Any], params: dict[str, Any], out_dir: Path):
        from fmriflow.preproc.backends.custom import CustomBackend
        from fmriflow.preproc.manifest import PreprocConfig

        config = PreprocConfig(
            subject=str(inputs.get("subject") or "unknown"),
            backend="custom",
            output_dir=self._output_dir(inputs, out_dir),
            bids_dir=str(inputs.get("input_dir") or "") or None,
            backend_params=dict(params),
        )
        return CustomBackend().collect(config)
