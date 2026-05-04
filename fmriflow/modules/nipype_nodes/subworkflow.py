"""Subworkflow placeholder node.

The runner intercepts ``node.type == "subworkflow"`` and executes the
saved workflow's inner graph, so this class' :meth:`run` is never invoked
in practice. It exists to register the type in the module registry and
provide ``PARAM_SCHEMA`` for the UI palette.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fmriflow.modules._decorators import nipype_node


@nipype_node("subworkflow")
class SubworkflowNode:
    """Embed a saved post-preproc workflow as a single node.

    Inputs and outputs are determined per-instance by the wrapped
    workflow's ``inputs:`` and ``outputs:`` declarations and surfaced as
    handles on the canvas.
    """

    INPUTS: list[str] = []
    OUTPUTS: list[str] = []

    PARAM_SCHEMA: dict[str, Any] = {
        "workflow_name": {
            "type": "str",
            "default": "",
            "description": "Name of a saved post-preproc workflow.",
        },
    }

    def run(
        self,
        inputs: dict[str, Path],
        out_dir: Path,
        params: dict[str, Any],
    ) -> dict[str, Path]:
        raise RuntimeError(
            "subworkflow.run() should never be called — the runner "
            "intercepts subworkflow nodes. Did you call this directly?"
        )
