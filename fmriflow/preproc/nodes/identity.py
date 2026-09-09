"""Identity — the no-op Stage-N transform.

Passes the previous stage's outputs through unchanged. Used to
smoke-test the registry + Protocol contract end-to-end without
depending on real preprocessing libraries (FSL, ANTs, nipype).

Real transforms (smooth, mask, regress) land in their own files
in this package and follow the same contract.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fmriflow.preproc.node_registry import preproc_node


@preproc_node("identity")
class IdentityTransform:
    """No-op transform — passes inputs through unchanged.

    Useful for testing the stack runner without doing real work,
    or as a copyable reference example for transform authors.
    """

    name = "identity"
    version = "0.1.0"
    description = "No-op transform — passes inputs through unchanged."

    INPUTS = ["in_file"]
    OUTPUTS = ["out_file"]
    PARAM_SCHEMA: dict = {}

    REQUIRED_PYTHON: list[str] = []
    REQUIRED_TOOLS: list[str] = []
    REQUIRED_ENV: list[str] = []
    CONTAINER: str | None = None

    def run(
        self,
        inputs: dict[str, Any],
        out_dir: Path,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        # No work — the "output" file is just the input file.
        # Stack runner records the StepRecord; nothing else happens.
        return {"out_file": inputs.get("in_file")}
