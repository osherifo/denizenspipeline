"""Template tiers: bundled with the package (read-only) and user-made.

A template is a complete graph a builder offers as a starting point.
Loading one produces an unsaved draft. User templates live in an
``$FMRIFLOW_HOME`` add-ons directory, carry no ``run_defaults`` (those are
dataset-specific) and may not shadow a bundled name, so the two lists never
disagree about what a name means.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Callable

import yaml

logger = logging.getLogger(__name__)

_SLUG_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_\-]*$")


def validate_slug(name: str) -> str:
    if not name or not _SLUG_RE.match(name):
        raise ValueError(f"invalid template name {name!r}: letters, digits, '_' and '-' only")
    return name


def concrete_path_warnings(graph: Any) -> list[str]:
    """Node params / literal inputs holding an absolute path.

    A template should take its paths from graph inputs (bound at run time);
    a literal ``/data/...`` typed into a node only works on the machine and
    dataset it was typed for.
    """
    def looks_like_path(v: Any) -> bool:
        return isinstance(v, str) and (v.startswith("/") or v.startswith("~"))

    out: list[str] = []
    for node in graph.nodes:
        for where, values in (("param", node.params), ("literal input", node.literal_inputs)):
            for key, v in values.items():
                candidates = v if isinstance(v, list) else [v]
                hits = [x for x in candidates if looks_like_path(x)]
                if hits:
                    out.append(f"{node.id}.{key} ({where}) holds a concrete path: {hits[0]}")
    return out


class TemplateTiers:
    """Bundled + user templates for one graph class.

    ``user_dir`` is called on every access so ``$FMRIFLOW_HOME`` changes
    (tests, the settings page) take effect without rebuilding the object.
    """

    def __init__(self, *, bundled_dir: Path, user_dir: Callable[[], Path], graph_cls: type) -> None:
        self.bundled_dir = Path(bundled_dir)
        self._user_dir = user_dir
        self.graph_cls = graph_cls

    def user_dir(self) -> Path:
        return self._user_dir()

    def is_graph_file(self, path: Path) -> bool:
        """True when the YAML holds a graph (``nodes``), not some other preset."""
        try:
            data = yaml.safe_load(Path(path).read_text()) or {}
        except Exception:
            return False
        if not isinstance(data, dict):
            return False
        return "nodes" in self.graph_cls.unwrap(data)

    def bundled_names(self) -> list[str]:
        return sorted(p.stem for p in self.bundled_dir.glob("*.yaml"))

    def user_names(self) -> list[str]:
        root = self.user_dir()
        files = sorted(root.glob("*.yaml")) + sorted(root.glob("*.yml"))
        return sorted({p.stem for p in files if self.is_graph_file(p)})

    def names(self) -> list[str]:
        return sorted(set(self.bundled_names()) | set(self.user_names()))

    def path(self, name: str) -> tuple[Path, str]:
        """Resolve ``name`` to ``(path, tier)``; ``KeyError`` when unknown."""
        bundled = self.bundled_dir / f"{name}.yaml"
        if bundled.exists():
            return bundled, "bundled"
        root = self.user_dir()
        for cand in (root / f"{name}.yaml", root / f"{name}.yml"):
            if cand.exists() and self.is_graph_file(cand):
                return cand, "user"
        raise KeyError(f"unknown template {name!r}; available: {', '.join(self.names())}")

    def load(self, name: str):
        path, _ = self.path(name)
        graph = self.graph_cls.load(path)
        if graph.name == "untitled":
            graph.name = name
        return graph

    def list(self) -> list[dict]:
        out = []
        for name in self.names():
            path, tier = self.path(name)
            try:
                graph = self.load(name)
            except Exception as e:  # a hand-edited user file that no longer parses
                logger.warning("template %s unreadable: %s", path, e)
                out.append({"name": name, "tier": tier, "description": "", "n_nodes": 0,
                            "node_types": [], "inputs": {}, "error": str(e)})
                continue
            out.append({
                "name": name,
                "tier": tier,
                "description": graph.description,
                "n_nodes": len(graph.nodes),
                "node_types": [n.type for n in graph.nodes],
                "inputs": graph.inputs,
                "error": None,
            })
        return out

    def save_user(self, name: str, graph: Any) -> Path:
        """Write ``graph`` as the user template ``name`` (run panel dropped).

        ``ValueError`` for a bad slug or a bundled name.
        """
        validate_slug(name)
        if name in self.bundled_names():
            raise ValueError(f"{name!r} is a bundled template; pick another name")
        graph.name = name
        graph.run_defaults = {}
        path = self.user_dir() / f"{name}.yaml"
        path.write_text(graph.to_yaml())
        return path

    def delete_user(self, name: str) -> bool:
        """Remove a user template; ``False`` when absent, ``ValueError`` for bundled."""
        validate_slug(name)
        if name in self.bundled_names():
            raise ValueError(f"{name!r} is a bundled template and cannot be deleted")
        root = self.user_dir()
        for cand in (root / f"{name}.yaml", root / f"{name}.yml"):
            if cand.exists():
                cand.unlink()
                return True
        return False
