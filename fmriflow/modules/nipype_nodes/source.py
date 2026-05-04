"""Source node — emits a file from the upstream PreprocManifest as input."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fmriflow.modules._decorators import nipype_node


@nipype_node("preproc_run")
class PreprocRunSourceNode:
    """Source: emit a single run's preprocessed BOLD file from the upstream manifest.

    Configure ``run_name`` to pick which run; the runner resolves the path
    against the source ``PreprocManifest.output_dir``.
    """

    INPUTS: list[str] = []
    OUTPUTS = ["out_file"]

    PARAM_SCHEMA: dict[str, Any] = {
        "run_name": {
            "type": "str",
            "default": "",
            "description": "run_name from the source PreprocManifest's runs[].",
        },
    }

    def run(
        self,
        inputs: dict[str, Path],
        out_dir: Path,
        params: dict[str, Any],
    ) -> dict[str, Path]:
        # The runner is responsible for resolving the source-manifest run and
        # populating ``params['_resolved_path']`` before calling us.
        resolved = params.get("_resolved_path")
        if not resolved:
            raise ValueError("preproc_run: runner did not resolve a source path")
        return {"out_file": Path(resolved)}
