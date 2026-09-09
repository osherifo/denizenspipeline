"""Pick one item (or a slice) out of a list output — e.g. the first BOLD run."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fmriflow.preproc.node_registry import preproc_node


@preproc_node("select")
class SelectNode:
    """Select ``index`` from a list input (negative indices count from the end)."""

    name = "select"
    version = "0.1.0"
    description = "Pick one item from a list output by index."
    INPUTS = {"inlist": {"kind": "any", "required": True, "description": "a list (or a single item)"}}
    OUTPUTS = {"out": {"kind": "file", "description": "the selected item"}}
    PARAM_SCHEMA: dict[str, Any] = {
        "index": {"type": "int", "default": 0, "description": "Which item to pick."},
    }
    REQUIRED_PYTHON: list[str] = []
    REQUIRED_TOOLS: list[str] = []
    REQUIRED_ENV: list[str] = []
    CONTAINER: str | None = None

    def run(self, inputs: dict[str, Any], out_dir: Path, params: dict[str, Any]) -> dict[str, Any]:
        value = inputs["inlist"]
        items = list(value) if isinstance(value, (list, tuple)) else [value]
        if not items:
            raise ValueError("select: input list is empty")
        idx = int(params.get("index", 0))
        try:
            return {"out": items[idx]}
        except IndexError:
            raise IndexError(f"select: index {idx} out of range for {len(items)} item(s)")
