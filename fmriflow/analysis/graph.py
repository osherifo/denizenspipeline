"""The analysis graph: typed nodes from the node catalog, plus graph globals.

``globals`` is the configuration every node's config is synthesised from
(see :mod:`fmriflow.analysis.adapters`): for a graph compiled from stage
YAML it is the full resolved config; for a graph built node by node it holds
the run-level values (experiment, subject, output directory, ...).

``stages`` lists stage records the run summary always carries, in order, so
a graph compiled from stage YAML reports every stage even when one has no
node (for example no reporters).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

from fmriflow.analysis.port_types import LATTICE
from fmriflow.graph.model import EdgeSpec, GraphSpec, NodeSpec
from fmriflow.graph.ports import port_type

SCOPES: tuple[str, ...] = ("subject", "group", "study")


@dataclass
class AnalysisNode(NodeSpec):
    pass


@dataclass
class AnalysisGraph(GraphSpec):
    nodes: list[AnalysisNode] = field(default_factory=list)
    edges: list[EdgeSpec] = field(default_factory=list)
    scope: str = "subject"
    globals: dict[str, Any] = field(default_factory=dict)
    stages: list[str] = field(default_factory=list)

    NODE_CLS: ClassVar[type] = AnalysisNode
    EDGE_CLS: ClassVar[type] = EdgeSpec
    WRAPPER_KEY: ClassVar[str] = "graph"
    NOUN: ClassVar[str] = "graph"
    CYCLE_MESSAGE: ClassVar[str] = "graph has a cycle"

    def _extra_to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"scope": self.scope}
        if self.globals:
            out["globals"] = dict(self.globals)
        if self.stages:
            out["stages"] = list(self.stages)
        return out

    @classmethod
    def _extra_from_dict(cls, data: dict[str, Any]) -> dict[str, Any]:
        return {
            "scope": str(data.get("scope") or "subject"),
            "globals": dict(data.get("globals") or {}),
            "stages": [str(s) for s in data.get("stages") or []],
        }

    def _edge_errors(self, edge, src, dst, src_port, dst_port, registry) -> list[str]:
        s, d = port_type(src_port), port_type(dst_port)
        if not LATTICE.compatible(s, d):
            return [f"edge {edge.id}: {src.id}.{edge.source_handle} ({s}) cannot feed "
                    f"{dst.id}.{edge.target_handle} ({d})"]
        return []

    def _validate_extra(self, registry: Any | None) -> list[str]:
        errors: list[str] = []
        if self.scope not in SCOPES:
            errors.append(f"unknown scope {self.scope!r}; expected one of {', '.join(SCOPES)}")
        from fmriflow.analysis.control import CONTROL_SCOPES
        for n in self.nodes:
            wanted = CONTROL_SCOPES.get(n.type)
            if wanted and wanted != self.scope:
                errors.append(f"node {n.id}: {n.type} belongs in a {wanted} graph, not a {self.scope} graph")
        if registry is None:
            return errors
        for n in self.nodes:
            ports = self._ports(n, registry)
            if ports is None:
                continue
            fed = {e.target_handle for e in self.predecessors(n.id)} | set(n.literal_inputs) | set(n.bindings)
            for port, spec in ports[0].items():
                if spec.get("required") and port not in fed:
                    errors.append(f"node {n.id}: required input {port!r} is not connected")
        return errors
