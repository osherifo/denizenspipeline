"""AnalysisGraphStore — saved analysis graphs.

Graphs live next to stage configs in the analysis configs directory and are
told apart by shape (a ``nodes:`` list, optionally under ``graph:``). This
store only reads and writes graph files; it refuses to overwrite or delete a
stage config of the same name.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from fmriflow.analysis.graph import AnalysisGraph
from fmriflow.graph.templates import validate_slug

logger = logging.getLogger(__name__)


def is_graph_document(data: object) -> bool:
    """True for a loaded YAML mapping holding an analysis graph."""
    return isinstance(data, dict) and "nodes" in AnalysisGraph.unwrap(data)


def is_graph_file(path: Path | str) -> bool:
    try:
        return is_graph_document(yaml.safe_load(Path(path).read_text()) or {})
    except Exception:
        return False


class AnalysisGraphStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _path(self, name: str) -> Path:
        validate_slug(name)
        return self.root / f"{name}.yaml"

    def list_graphs(self) -> list[dict]:
        if not self.root.is_dir():
            return []
        rows = []
        for path in sorted(self.root.glob("*.yaml")):
            if path.name.startswith("_") or not is_graph_file(path):
                continue
            try:
                graph = AnalysisGraph.load(path)
            except Exception as e:  # hand-edited file that no longer parses
                logger.warning("analysis graph %s unreadable: %s", path, e)
                rows.append({"name": path.stem, "path": str(path), "scope": "", "description": "",
                             "n_nodes": 0, "node_types": [], "inputs": {}, "error": str(e)})
                continue
            rows.append({
                "name": path.stem,
                "path": str(path),
                "scope": graph.scope,
                "description": graph.description,
                "n_nodes": len(graph.nodes),
                "node_types": [n.type for n in graph.nodes],
                "inputs": graph.inputs,
                "error": None,
            })
        return rows

    def load(self, name: str) -> AnalysisGraph:
        """The saved graph ``name``; ``KeyError`` when absent or not a graph."""
        path = self._path(name)
        if not path.is_file() or not is_graph_file(path):
            raise KeyError(f"no analysis graph named {name!r}")
        graph = AnalysisGraph.load(path)
        if graph.name == "untitled":
            graph.name = name
        return graph

    def save(self, name: str, graph: AnalysisGraph) -> Path:
        """Write ``graph`` as ``<name>.yaml``; ``ValueError`` for a bad name or a stage config in the way."""
        path = self._path(name)
        if path.exists() and not is_graph_file(path):
            raise ValueError(f"{path.name} is a stage config; save the graph under another name")
        self.root.mkdir(parents=True, exist_ok=True)
        path.write_text(graph.to_yaml())
        return path

    def delete(self, name: str) -> bool:
        path = self._path(name)
        if not path.exists():
            return False
        if not is_graph_file(path):
            raise ValueError(f"{path.name} is a stage config, not a graph")
        path.unlink()
        return True
