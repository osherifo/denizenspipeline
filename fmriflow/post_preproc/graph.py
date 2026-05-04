"""Post-preproc graph: ReactFlow-shape nodes/edges with topology helpers.

The shape mirrors what the frontend's @xyflow/react ships, so the graph
round-trips between UI and server without reshaping::

    {
      "nodes": [
        {"id": "n1", "type": "smooth", "data": {"params": {...}}, "position": {...}},
        ...
      ],
      "edges": [
        {"id": "e1", "source": "n1", "target": "n2",
         "sourceHandle": "out_file", "targetHandle": "in_file"}
      ]
    }
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GraphNode:
    id: str
    type: str
    params: dict[str, Any] = field(default_factory=dict)
    position: dict[str, float] = field(default_factory=dict)


@dataclass
class GraphEdge:
    id: str
    source: str
    target: str
    source_handle: str = "out_file"
    target_handle: str = "in_file"


@dataclass
class PostPreprocGraph:
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)

    # ── ReactFlow JSON round-trip ───────────────────────────────────

    @classmethod
    def from_reactflow(cls, data: dict[str, Any]) -> PostPreprocGraph:
        nodes = []
        for n in data.get("nodes", []):
            d = n.get("data") or {}
            nodes.append(
                GraphNode(
                    id=n["id"],
                    type=n["type"],
                    params=d.get("params", {}) or {},
                    position=n.get("position", {}) or {},
                )
            )
        edges = []
        for e in data.get("edges", []):
            edges.append(
                GraphEdge(
                    id=e["id"],
                    source=e["source"],
                    target=e["target"],
                    source_handle=e.get("sourceHandle") or "out_file",
                    target_handle=e.get("targetHandle") or "in_file",
                )
            )
        return cls(nodes=nodes, edges=edges)

    def to_reactflow(self) -> dict[str, Any]:
        return {
            "nodes": [
                {
                    "id": n.id,
                    "type": n.type,
                    "data": {"params": n.params},
                    "position": n.position or {"x": 0, "y": 0},
                }
                for n in self.nodes
            ],
            "edges": [
                {
                    "id": e.id,
                    "source": e.source,
                    "target": e.target,
                    "sourceHandle": e.source_handle,
                    "targetHandle": e.target_handle,
                }
                for e in self.edges
            ],
        }

    # ── topology ────────────────────────────────────────────────────

    def topo_order(self) -> list[GraphNode]:
        """Kahn's algorithm. Raises ValueError on cycles."""
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
            raise ValueError("Graph has a cycle")

        by_id = {n.id: n for n in self.nodes}
        return [by_id[i] for i in ordered]

    def predecessors(self, node_id: str) -> list[GraphEdge]:
        """All edges that feed into node_id."""
        return [e for e in self.edges if e.target == node_id]

    # ── validation ──────────────────────────────────────────────────

    def validate_against(self, node_specs: dict[str, Any]) -> list[str]:
        """Return a list of error strings; empty if valid.

        ``node_specs`` maps node-type name -> a class with INPUTS/OUTPUTS lists.
        """
        errors: list[str] = []
        seen_ids: set[str] = set()
        for n in self.nodes:
            if n.id in seen_ids:
                errors.append(f"Duplicate node id: {n.id}")
            seen_ids.add(n.id)
            if n.type not in node_specs:
                errors.append(f"Unknown node type: {n.type!r} (id={n.id})")

        ids = {n.id for n in self.nodes}
        for e in self.edges:
            if e.source not in ids:
                errors.append(f"Edge {e.id} references unknown source {e.source!r}")
            if e.target not in ids:
                errors.append(f"Edge {e.id} references unknown target {e.target!r}")
            tnode = next((n for n in self.nodes if n.id == e.target), None)
            if tnode and tnode.type in node_specs:
                spec = node_specs[tnode.type]
                inputs = getattr(spec, "INPUTS", [])
                if e.target_handle not in inputs:
                    errors.append(
                        f"Edge {e.id}: target handle {e.target_handle!r} "
                        f"not in {tnode.type}.INPUTS={inputs}"
                    )
            snode = next((n for n in self.nodes if n.id == e.source), None)
            if snode and snode.type in node_specs:
                spec = node_specs[snode.type]
                outputs = getattr(spec, "OUTPUTS", [])
                if e.source_handle not in outputs:
                    errors.append(
                        f"Edge {e.id}: source handle {e.source_handle!r} "
                        f"not in {snode.type}.OUTPUTS={outputs}"
                    )

        # Cycle check
        try:
            self.topo_order()
        except ValueError as ex:
            errors.append(str(ex))

        return errors
