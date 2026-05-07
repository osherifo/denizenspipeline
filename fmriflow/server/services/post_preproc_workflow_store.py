"""Disk-backed registry of saved post-preproc workflows.

Each workflow is one YAML file at::

    {root}/<name>.yaml

Default root is ``~/.fmriflow/post_preproc_workflows/``. The YAML wraps
the existing ReactFlow-shape graph::

    name: smooth_then_mask
    description: Optional one-liner.
    inputs:
      in_file: { from: smo.in_file }
    outputs:
      out_file: { from: msk.out_file }
    graph:
      nodes: [...]
      edges: [...]
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")


def _safe(name: str) -> str:
    if not name or not _SAFE_NAME.match(name):
        raise ValueError(f"Unsafe workflow name: {name!r}")
    return name


class PostPreprocWorkflowStore:
    """List/get/save/delete YAML workflows on disk."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def _path(self, name: str) -> Path:
        return self.root / f"{_safe(name)}.yaml"

    def list(self) -> list[dict[str, Any]]:
        if not self.root.is_dir():
            return []
        out: list[dict[str, Any]] = []
        for p in sorted(self.root.glob("*.yaml")):
            try:
                data = yaml.safe_load(p.read_text()) or {}
            except yaml.YAMLError as e:
                logger.warning("Bad workflow YAML %s: %s", p, e)
                continue
            if not isinstance(data, dict):
                continue
            out.append({
                "name": data.get("name", p.stem),
                "description": data.get("description", ""),
                "inputs": list((data.get("inputs") or {}).keys()),
                "outputs": list((data.get("outputs") or {}).keys()),
                "n_nodes": len(((data.get("graph") or {}).get("nodes") or [])),
            })
        return out

    def get(self, name: str) -> dict[str, Any] | None:
        p = self._path(name)
        if not p.is_file():
            return None
        try:
            data = yaml.safe_load(p.read_text()) or {}
        except yaml.YAMLError as e:
            logger.warning("Bad workflow YAML %s: %s", p, e)
            return None
        if not isinstance(data, dict):
            return None
        # Normalize.
        data.setdefault("name", name)
        data.setdefault("description", "")
        data.setdefault("inputs", {})
        data.setdefault("outputs", {})
        data.setdefault("graph", {"nodes": [], "edges": []})
        return data

    def save(
        self,
        name: str,
        graph: dict[str, Any],
        *,
        description: str = "",
        inputs: dict[str, Any] | None = None,
        outputs: dict[str, Any] | None = None,
    ) -> Path:
        p = self._path(name)
        p.parent.mkdir(parents=True, exist_ok=True)
        body = {
            "name": _safe(name),
            "description": description,
            "inputs": inputs or {},
            "outputs": outputs or {},
            "graph": graph,
        }
        p.write_text(yaml.safe_dump(body, sort_keys=False))
        return p

    def delete(self, name: str) -> bool:
        p = self._path(name)
        if not p.is_file():
            return False
        p.unlink()
        return True
