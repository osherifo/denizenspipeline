"""Node / edge / graph model with ReactFlow-compatible serialisation.

The JSON shape stays ReactFlow-compatible so a graphical builder
round-trips it without reshaping::

    {"schema_version": 1, "name": "demo",
     "inputs": {"subject": {"kind": "str"}},
     "nodes": [{"id": "a", "type": "some_type", "kind": "",
                "data": {"params": {...}, "bindings": {"x": "$inputs.subject"}},
                "position": {"x": 0, "y": 0}}],
     "edges": [{"id": "e1", "source": "a", "sourceHandle": "out",
                "target": "b", "targetHandle": "in"}]}

Subclasses add node data fields (``data_to_dict`` / ``data_from_dict``),
top-level graph keys (``_extra_to_dict`` / ``_extra_from_dict``) and
validation rules (``_node_errors``, ``_edge_errors``, ``_validate_extra``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

import yaml

from fmriflow.graph.ports import PortSpec, accepts_many

SCHEMA_VERSION = 1

# Reference prefix a node binding uses to pull a graph-level input.
INPUT_REF_PREFIX = "$inputs."


class _NoAliasDumper(yaml.SafeDumper):
    """Safe dumper that writes shared values out in full instead of ``&id001`` anchors.

    A graph compiled from a config shares lists between node params and
    ``globals``; anchors would make the YAML hard to read and edit by hand.
    """

    def ignore_aliases(self, data: Any) -> bool:
        return True


@dataclass
class NodeSpec:
    id: str
    type: str                       # registry name of the node type
    kind: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    literal_inputs: dict[str, Any] = field(default_factory=dict)
    bindings: dict[str, str] = field(default_factory=dict)   # port -> "$inputs.<name>"
    position: dict[str, float] = field(default_factory=dict)

    DEFAULT_KIND: ClassVar[str] = ""

    def data_to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"params": dict(self.params)}
        if self.literal_inputs:
            data["literal_inputs"] = dict(self.literal_inputs)
        if self.bindings:
            data["bindings"] = dict(self.bindings)
        return data

    @classmethod
    def data_from_dict(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Constructor kwargs for the fields stored under ``data``."""
        return {
            "params": dict(data.get("params") or {}),
            "literal_inputs": dict(data.get("literal_inputs") or {}),
            "bindings": dict(data.get("bindings") or {}),
        }

    def to_reactflow(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "kind": self.kind,
            "data": self.data_to_dict(),
            "position": dict(self.position) or {"x": 0.0, "y": 0.0},
        }

    @classmethod
    def from_reactflow(cls, n: dict[str, Any]):
        return cls(
            id=str(n["id"]),
            type=str(n["type"]),
            kind=str(n.get("kind") or cls.DEFAULT_KIND),
            position=dict(n.get("position") or {}),
            **cls.data_from_dict(n.get("data") or {}),
        )


@dataclass
class EdgeSpec:
    id: str
    source: str
    target: str
    source_handle: str = ""
    target_handle: str = ""

    DEFAULT_SOURCE_HANDLE: ClassVar[str] = ""
    DEFAULT_TARGET_HANDLE: ClassVar[str] = ""

    def to_reactflow(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "sourceHandle": self.source_handle,
            "targetHandle": self.target_handle,
        }

    @classmethod
    def from_reactflow(cls, e: dict[str, Any]):
        return cls(
            id=str(e["id"]),
            source=str(e["source"]),
            target=str(e["target"]),
            source_handle=str(e.get("sourceHandle") or cls.DEFAULT_SOURCE_HANDLE),
            target_handle=str(e.get("targetHandle") or cls.DEFAULT_TARGET_HANDLE),
        )


@dataclass
class GraphSpec:
    name: str = "untitled"
    description: str = ""
    inputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    nodes: list[NodeSpec] = field(default_factory=list)
    edges: list[EdgeSpec] = field(default_factory=list)
    # Run-panel values saved with the graph so a saved config is a complete,
    # re-runnable thing. Templates carry none.
    run_defaults: dict[str, Any] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    NODE_CLS: ClassVar[type] = NodeSpec
    EDGE_CLS: ClassVar[type] = EdgeSpec
    SUPPORTED_SCHEMA: ClassVar[int] = SCHEMA_VERSION
    # Top-level key a YAML file may wrap the graph in (e.g. ``pipeline:``).
    WRAPPER_KEY: ClassVar[str | None] = None
    # Word used in messages ("pipeline YAML must be a mapping").
    NOUN: ClassVar[str] = "graph"
    CYCLE_MESSAGE: ClassVar[str] = "graph has a cycle"

    # ── serialisation ──────────────────────────────────────────────

    def _extra_to_dict(self) -> dict[str, Any]:
        """Subclass hook: top-level keys written after ``edges``."""
        return {}

    @classmethod
    def _extra_from_dict(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Subclass hook: constructor kwargs for the extra top-level keys."""
        return {}

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "schema_version": self.schema_version,
            "name": self.name,
            "description": self.description,
            "inputs": {k: dict(v) for k, v in self.inputs.items()},
            "outputs": {k: dict(v) for k, v in self.outputs.items()},
            "nodes": [n.to_reactflow() for n in self.nodes],
            "edges": [e.to_reactflow() for e in self.edges],
        }
        out.update(self._extra_to_dict())
        if self.run_defaults:
            out["run_defaults"] = dict(self.run_defaults)
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]):
        version = int(data.get("schema_version") or SCHEMA_VERSION)
        if version > cls.SUPPORTED_SCHEMA:
            raise ValueError(
                f"{cls.NOUN} schema_version {version} is newer than supported {cls.SUPPORTED_SCHEMA}"
            )
        return cls(
            name=str(data.get("name") or "untitled"),
            description=str(data.get("description") or ""),
            inputs={k: dict(v or {}) for k, v in (data.get("inputs") or {}).items()},
            outputs={k: dict(v or {}) for k, v in (data.get("outputs") or {}).items()},
            nodes=[cls.NODE_CLS.from_reactflow(n) for n in data.get("nodes") or []],
            edges=[cls.EDGE_CLS.from_reactflow(e) for e in data.get("edges") or []],
            run_defaults={k: v for k, v in (data.get("run_defaults") or {}).items() if v not in (None, "", [])},
            schema_version=version,
            **cls._extra_from_dict(data),
        )

    def to_yaml(self) -> str:
        return yaml.dump(self.to_dict(), Dumper=_NoAliasDumper, sort_keys=False)

    @classmethod
    def unwrap(cls, data: dict[str, Any]) -> dict[str, Any]:
        key = cls.WRAPPER_KEY
        if key and key in data and isinstance(data[key], dict) and "nodes" not in data:
            return data[key]
        return data

    @classmethod
    def from_yaml(cls, text: str):
        data = yaml.safe_load(text) or {}
        if not isinstance(data, dict):
            raise ValueError(f"{cls.NOUN} YAML must be a mapping")
        return cls.from_dict(cls.unwrap(data))

    @classmethod
    def load(cls, path: Path | str):
        return cls.from_yaml(Path(path).read_text())

    def save(self, path: Path | str) -> None:
        Path(path).write_text(self.to_yaml())

    # ── lookup ────────────────────────────────────────────────────

    def node(self, node_id: str):
        for n in self.nodes:
            if n.id == node_id:
                return n
        raise KeyError(f"no node with id {node_id!r}")

    def has_node(self, node_id: str) -> bool:
        return any(n.id == node_id for n in self.nodes)

    # ── topology ───────────────────────────────────────────────────

    def predecessors(self, node_id: str) -> list:
        """All edges feeding ``node_id``, in edge-list order."""
        return [e for e in self.edges if e.target == node_id]

    def successors(self, node_id: str) -> list:
        """All edges leaving ``node_id``."""
        return [e for e in self.edges if e.source == node_id]

    def topo_order(self) -> list:
        """Kahn's algorithm. Raises ``ValueError`` on a cycle."""
        in_degree: dict[str, int] = {n.id: 0 for n in self.nodes}
        adj: dict[str, list[str]] = {n.id: [] for n in self.nodes}
        for e in self.edges:
            if e.target in in_degree:
                in_degree[e.target] += 1
            if e.source in adj:
                adj[e.source].append(e.target)

        queue = [nid for nid, d in in_degree.items() if d == 0]
        ordered: list[str] = []
        while queue:
            nid = queue.pop(0)
            ordered.append(nid)
            for nxt in adj.get(nid, []):
                in_degree[nxt] -= 1
                if in_degree[nxt] == 0:
                    queue.append(nxt)

        if len(ordered) != len(self.nodes):
            raise ValueError(self.CYCLE_MESSAGE)

        by_id = {n.id: n for n in self.nodes}
        return [by_id[i] for i in ordered]

    def descendants(self, node_ids: list[str] | set[str]) -> set[str]:
        """``node_ids`` plus everything downstream of them."""
        seen: set[str] = set()
        stack = list(node_ids)
        while stack:
            nid = stack.pop()
            if nid in seen:
                continue
            seen.add(nid)
            stack.extend(e.target for e in self.successors(nid))
        return seen

    def is_linear(self) -> bool:
        """True when the graph is a single path. A single node counts."""
        if not self.nodes:
            return True
        if len(self.edges) != len(self.nodes) - 1:
            return False
        in_count: dict[str, int] = {n.id: 0 for n in self.nodes}
        out_count: dict[str, int] = {n.id: 0 for n in self.nodes}
        for e in self.edges:
            if e.source not in out_count or e.target not in in_count:
                return False
            out_count[e.source] += 1
            in_count[e.target] += 1
        if any(c > 1 for c in in_count.values()) or any(c > 1 for c in out_count.values()):
            return False
        try:
            self.topo_order()
        except ValueError:
            return False
        return True

    # ── validation ─────────────────────────────────────────────────

    def _ports(self, node: NodeSpec, registry: Any | None) -> tuple[dict[str, PortSpec], dict[str, PortSpec]] | None:
        """(inputs, outputs) for ``node``, or ``None`` when unknown.

        Uses ``registry.node_ports(node)`` when the registry has it (ports that
        depend on node params, e.g. a fan-out node exposing its body's
        outputs), else ``registry.ports(node.type)``.
        """
        if registry is None or not registry.has(node.type):
            return None
        node_ports = getattr(registry, "node_ports", None)
        if callable(node_ports):
            return node_ports(node)
        return registry.ports(node.type)

    def _node_errors(self, node: NodeSpec, registry: Any | None) -> list[str]:
        """Subclass hook: per-node checks beyond ids and bindings."""
        if registry is not None and not registry.has(node.type):
            return [f"node {node.id}: unknown node type {node.type!r}"]
        return []

    def _edge_errors(self, edge: EdgeSpec, src: NodeSpec, dst: NodeSpec,
                     src_port: PortSpec, dst_port: PortSpec, registry: Any | None) -> list[str]:
        """Subclass hook: checks on an edge whose two ports both exist (e.g. types)."""
        return []

    def _validate_extra(self, registry: Any | None) -> list[str]:
        """Subclass hook: graph-wide checks run before the cycle check."""
        return []

    def validate(self, registry: Any | None = None) -> list[str]:
        """Return a list of error strings; empty means valid.

        ``registry`` is any object with ``has(name)`` and
        ``ports(name) -> (inputs, outputs)`` (optionally ``node_ports(node)``
        and ``kind(name)``). Without one, only the structural checks run.
        """
        errors: list[str] = []
        seen: set[str] = set()
        for n in self.nodes:
            if not n.id:
                errors.append("a node has an empty id")
            if n.id in seen:
                errors.append(f"duplicate node id: {n.id}")
            seen.add(n.id)
            errors.extend(self._node_errors(n, registry))
            for port, ref in n.bindings.items():
                if not isinstance(ref, str) or not ref.startswith(INPUT_REF_PREFIX):
                    errors.append(
                        f"node {n.id}: binding for {port!r} must be "
                        f"'{INPUT_REF_PREFIX}<name>', got {ref!r}"
                    )
                elif ref[len(INPUT_REF_PREFIX):] not in self.inputs:
                    errors.append(
                        f"node {n.id}: binding {ref!r} names an undeclared {self.NOUN} input"
                    )

        ids = {n.id for n in self.nodes}
        edge_ids: set[str] = set()
        for e in self.edges:
            if e.id in edge_ids:
                errors.append(f"duplicate edge id: {e.id}")
            edge_ids.add(e.id)
            if e.source not in ids:
                errors.append(f"edge {e.id}: unknown source {e.source!r}")
            if e.target not in ids:
                errors.append(f"edge {e.id}: unknown target {e.target!r}")
            if registry is None or e.source not in ids or e.target not in ids:
                continue
            src, dst = self.node(e.source), self.node(e.target)
            dst_ports, src_ports = self._ports(dst, registry), self._ports(src, registry)
            dst_spec = src_spec = None
            if dst_ports is not None:
                inputs = dst_ports[0]
                if e.target_handle not in inputs:
                    errors.append(
                        f"edge {e.id}: target handle {e.target_handle!r} not in "
                        f"{dst.type}.INPUTS={sorted(inputs)}"
                    )
                else:
                    dst_spec = inputs[e.target_handle]
            if src_ports is not None:
                outputs = src_ports[1]
                if e.source_handle not in outputs:
                    errors.append(
                        f"edge {e.id}: source handle {e.source_handle!r} not in "
                        f"{src.type}.OUTPUTS={sorted(outputs)}"
                    )
                else:
                    src_spec = outputs[e.source_handle]
            if src_spec is not None and dst_spec is not None:
                errors.extend(self._edge_errors(e, src, dst, src_spec, dst_spec, registry))

        # Every input port gets at most one feed (edge, literal or binding),
        # except ports declared ``multiple``, which take several edges.
        for n in self.nodes:
            fed: dict[str, list[str]] = {}
            for e in self.predecessors(n.id):
                fed.setdefault(e.target_handle, []).append(f"edge {e.id}")
            for port in n.literal_inputs:
                fed.setdefault(port, []).append("literal")
            for port in n.bindings:
                fed.setdefault(port, []).append("binding")
            ports = None
            for port, feeds in fed.items():
                if len(feeds) <= 1:
                    continue
                if ports is None:
                    ports = self._ports(n, registry) or ({}, {})
                if accepts_many(ports[0].get(port)) and all(f.startswith("edge ") for f in feeds):
                    continue
                errors.append(
                    f"node {n.id}: input {port!r} is fed more than once ({', '.join(feeds)})"
                )

        errors.extend(self._validate_extra(registry))

        try:
            self.topo_order()
        except ValueError as ex:
            errors.append(str(ex))

        return errors
