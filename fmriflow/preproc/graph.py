"""Pipeline graph — the one model for a preprocessing pipeline.

A preprocessing pipeline is a DAG of nodes drawn from the node library
(:mod:`fmriflow.preproc.node_registry`). fmriprep, a BIDS-app, a shell
command, a single transform, an imported nipype workflow and a
user-authored node are all just nodes here; the runner turns the whole
graph into one nipype ``Workflow``.

The JSON shape stays ReactFlow-compatible so the builder round-trips it
without reshaping::

    {
      "schema_version": 1,
      "name": "fmriprep_smooth",
      "inputs":  {"bids_dir": {"kind": "dir"}, "subject": {"kind": "str"}},
      "nodes": [
        {"id": "fp", "type": "fmriprep", "kind": "container_app",
         "data": {"params": {...}, "bindings": {"bids_dir": "$inputs.bids_dir"}},
         "position": {"x": 0, "y": 0}},
        {"id": "smooth", "type": "smooth", "kind": "interface",
         "data": {"params": {"fwhm": 5.0}, "literal_inputs": {}, "iter": null}}
      ],
      "edges": [{"id": "e1", "source": "fp", "sourceHandle": "bold_preproc",
                 "target": "smooth", "targetHandle": "in_file"}],
      "manifest": {"backend_node": "fp", "bold_from": "smooth.out_file"}
    }

Subject / path bindings are **not** part of the pipeline — they live in
:class:`PipelineRunRequest`, so one pipeline runs on any subject.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Literal

import yaml

SCHEMA_VERSION = 1

NodeKind = Literal["interface", "container_app", "composite", "source"]
NODE_KINDS: tuple[str, ...] = ("interface", "container_app", "composite", "source")

# Reference prefix a node binding uses to pull a pipeline-level input.
INPUT_REF_PREFIX = "$inputs."


def iter_handles(spec: dict[str, Any] | None) -> list[str]:
    """The ports an ``iter`` block maps over (``handle`` or ``handles``)."""
    if not spec:
        return []
    if spec.get("handles"):
        return [str(h) for h in spec["handles"]]
    if spec.get("handle"):
        return [str(spec["handle"])]
    return []


@dataclass
class PipelineNode:
    id: str
    type: str                       # node-library name
    kind: str = "interface"         # NodeKind; validated against the library
    params: dict[str, Any] = field(default_factory=dict)
    literal_inputs: dict[str, Any] = field(default_factory=dict)
    bindings: dict[str, str] = field(default_factory=dict)   # port -> "$inputs.<name>"
    iter: dict[str, Any] | None = None    # {"handle": "<port>"} or {"handles": [...]} (+ optional literal "values")
    # Pipeline-level checkpoint entries: {step, artifact, metric, norms?, live?, enabled?}
    checks: list[dict[str, Any]] = field(default_factory=list)
    position: dict[str, float] = field(default_factory=dict)

    def to_reactflow(self) -> dict[str, Any]:
        data: dict[str, Any] = {"params": dict(self.params)}
        if self.literal_inputs:
            data["literal_inputs"] = dict(self.literal_inputs)
        if self.bindings:
            data["bindings"] = dict(self.bindings)
        if self.iter is not None:
            data["iter"] = dict(self.iter)
        if self.checks:
            data["checks"] = [dict(c) for c in self.checks]
        return {
            "id": self.id,
            "type": self.type,
            "kind": self.kind,
            "data": data,
            "position": dict(self.position) or {"x": 0.0, "y": 0.0},
        }

    @classmethod
    def from_reactflow(cls, n: dict[str, Any]) -> PipelineNode:
        d = n.get("data") or {}
        it = d.get("iter")
        return cls(
            id=str(n["id"]),
            type=str(n["type"]),
            kind=str(n.get("kind") or "interface"),
            params=dict(d.get("params") or {}),
            literal_inputs=dict(d.get("literal_inputs") or {}),
            bindings=dict(d.get("bindings") or {}),
            iter=dict(it) if isinstance(it, dict) else None,
            checks=[dict(c) for c in (d.get("checks") or []) if isinstance(c, dict)],
            position=dict(n.get("position") or {}),
        )


@dataclass
class PipelineEdge:
    id: str
    source: str
    target: str
    source_handle: str = "out_file"
    target_handle: str = "in_file"

    def to_reactflow(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "sourceHandle": self.source_handle,
            "targetHandle": self.target_handle,
        }

    @classmethod
    def from_reactflow(cls, e: dict[str, Any]) -> PipelineEdge:
        return cls(
            id=str(e["id"]),
            source=str(e["source"]),
            target=str(e["target"]),
            source_handle=str(e.get("sourceHandle") or "out_file"),
            target_handle=str(e.get("targetHandle") or "in_file"),
        )


@dataclass
class Pipeline:
    name: str = "untitled"
    description: str = ""
    inputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    nodes: list[PipelineNode] = field(default_factory=list)
    edges: list[PipelineEdge] = field(default_factory=list)
    manifest: dict[str, Any] = field(default_factory=dict)
    # Run-panel values saved with the pipeline (subject, bids_dir, output_dir,
    # work_dir, plugin, …) so a saved config is a complete, re-runnable thing.
    # Templates carry none; the CLI and the workflow stage use them as
    # fallbacks for anything not given explicitly.
    run_defaults: dict[str, Any] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    # ── serialisation ──────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        out = {
            "schema_version": self.schema_version,
            "name": self.name,
            "description": self.description,
            "inputs": {k: dict(v) for k, v in self.inputs.items()},
            "outputs": {k: dict(v) for k, v in self.outputs.items()},
            "nodes": [n.to_reactflow() for n in self.nodes],
            "edges": [e.to_reactflow() for e in self.edges],
            "manifest": dict(self.manifest),
        }
        if self.run_defaults:
            out["run_defaults"] = dict(self.run_defaults)
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Pipeline:
        version = int(data.get("schema_version") or SCHEMA_VERSION)
        if version > SCHEMA_VERSION:
            raise ValueError(
                f"pipeline schema_version {version} is newer than supported {SCHEMA_VERSION}"
            )
        return cls(
            name=str(data.get("name") or "untitled"),
            description=str(data.get("description") or ""),
            inputs={k: dict(v or {}) for k, v in (data.get("inputs") or {}).items()},
            outputs={k: dict(v or {}) for k, v in (data.get("outputs") or {}).items()},
            nodes=[PipelineNode.from_reactflow(n) for n in data.get("nodes") or []],
            edges=[PipelineEdge.from_reactflow(e) for e in data.get("edges") or []],
            manifest=dict(data.get("manifest") or {}),
            run_defaults={k: v for k, v in (data.get("run_defaults") or {}).items() if v not in (None, "", [])},
            schema_version=version,
        )

    def to_yaml(self) -> str:
        return yaml.safe_dump(self.to_dict(), sort_keys=False)

    @classmethod
    def from_yaml(cls, text: str) -> Pipeline:
        data = yaml.safe_load(text) or {}
        if not isinstance(data, dict):
            raise ValueError("pipeline YAML must be a mapping")
        # Accept a `pipeline:` wrapper, matching the other stage configs.
        if "pipeline" in data and isinstance(data["pipeline"], dict) and "nodes" not in data:
            data = data["pipeline"]
        return cls.from_dict(data)

    @classmethod
    def load(cls, path: Path | str) -> Pipeline:
        return cls.from_yaml(Path(path).read_text())

    def save(self, path: Path | str) -> None:
        Path(path).write_text(self.to_yaml())

    # ── lookup ────────────────────────────────────────────────────

    def node(self, node_id: str) -> PipelineNode:
        for n in self.nodes:
            if n.id == node_id:
                return n
        raise KeyError(f"no node with id {node_id!r}")

    def has_node(self, node_id: str) -> bool:
        return any(n.id == node_id for n in self.nodes)

    # ── topology ───────────────────────────────────────────────────

    def predecessors(self, node_id: str) -> list[PipelineEdge]:
        """All edges feeding ``node_id``."""
        return [e for e in self.edges if e.target == node_id]

    def successors(self, node_id: str) -> list[PipelineEdge]:
        """All edges leaving ``node_id``."""
        return [e for e in self.edges if e.source == node_id]

    def topo_order(self) -> list[PipelineNode]:
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
            raise ValueError("pipeline graph has a cycle")

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
        """True when the graph is a single path (what the Simple view shows).

        Every node has at most one incoming and one outgoing edge, and the
        edges connect the nodes into one chain. A single node counts.
        """
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

    def validate(self, registry: Any | None = None) -> list[str]:
        """Return a list of error strings; empty means valid.

        ``registry`` is a :class:`~fmriflow.preproc.node_registry.NodeRegistry`
        (or any object with ``has(name)``, ``kind(name)`` and
        ``ports(name) -> (inputs, outputs)``). Without one, only the
        structural checks run.
        """
        errors: list[str] = []
        seen: set[str] = set()
        for n in self.nodes:
            if not n.id:
                errors.append("a node has an empty id")
            if n.id in seen:
                errors.append(f"duplicate node id: {n.id}")
            seen.add(n.id)
            if n.kind not in NODE_KINDS:
                errors.append(f"node {n.id}: unknown kind {n.kind!r}")
            if registry is not None:
                if not registry.has(n.type):
                    errors.append(f"node {n.id}: unknown node type {n.type!r}")
                else:
                    lib_kind = registry.kind(n.type)
                    if lib_kind != n.kind:
                        errors.append(
                            f"node {n.id}: kind {n.kind!r} does not match "
                            f"library kind {lib_kind!r} for {n.type!r}"
                        )
            for port, ref in n.bindings.items():
                if not isinstance(ref, str) or not ref.startswith(INPUT_REF_PREFIX):
                    errors.append(
                        f"node {n.id}: binding for {port!r} must be "
                        f"'{INPUT_REF_PREFIX}<name>', got {ref!r}"
                    )
                elif ref[len(INPUT_REF_PREFIX):] not in self.inputs:
                    errors.append(
                        f"node {n.id}: binding {ref!r} names an undeclared pipeline input"
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
            if registry.has(dst.type):
                inputs, _ = registry.ports(dst.type)
                if e.target_handle not in inputs:
                    errors.append(
                        f"edge {e.id}: target handle {e.target_handle!r} not in "
                        f"{dst.type}.INPUTS={sorted(inputs)}"
                    )
            if registry.has(src.type):
                _, outputs = registry.ports(src.type)
                if e.source_handle not in outputs:
                    errors.append(
                        f"edge {e.id}: source handle {e.source_handle!r} not in "
                        f"{src.type}.OUTPUTS={sorted(outputs)}"
                    )

        # Every input port gets at most one feed (edge, literal or binding).
        for n in self.nodes:
            fed: dict[str, list[str]] = {}
            for e in self.predecessors(n.id):
                fed.setdefault(e.target_handle, []).append(f"edge {e.id}")
            for port in n.literal_inputs:
                fed.setdefault(port, []).append("literal")
            for port in n.bindings:
                fed.setdefault(port, []).append("binding")
            for port, feeds in fed.items():
                if len(feeds) > 1:
                    errors.append(
                        f"node {n.id}: input {port!r} is fed more than once ({', '.join(feeds)})"
                    )

        for n in self.nodes:
            if n.iter is None:
                continue
            handles = iter_handles(n.iter)
            if not handles:
                errors.append(f"node {n.id}: iter needs a 'handle' (or 'handles')")
                continue
            for handle in handles:
                if registry is not None and registry.has(n.type):
                    inputs, _ = registry.ports(n.type)
                    if handle not in inputs:
                        errors.append(
                            f"node {n.id}: iter handle {handle!r} not in "
                            f"{n.type}.INPUTS={sorted(inputs)}"
                        )
                # The list to iterate over arrives on the handle's edge, or is
                # given literally as ``values``; one of the two must be there.
                fed_by_edge = any(e.target_handle == handle for e in self.predecessors(n.id))
                if not fed_by_edge and "values" not in n.iter:
                    errors.append(
                        f"node {n.id}: iter handle {handle!r} needs an incoming edge or literal 'values'"
                    )

        backend_node = self.manifest.get("backend_node")
        if backend_node and backend_node not in ids:
            errors.append(f"manifest.backend_node {backend_node!r} is not a node id")
        for key in ("bold_from", "confounds_from", "mask_from"):
            ref = self.manifest.get(key)
            if ref:
                nid, _, port = str(ref).partition(".")
                if nid not in ids or not port:
                    errors.append(f"manifest.{key} {ref!r} must be '<node_id>.<port>'")

        try:
            self.topo_order()
        except ValueError as ex:
            errors.append(str(ex))

        return errors


@dataclass
class PipelineRunRequest:
    """Everything a run needs that is *not* part of the pipeline.

    The run manager persists this next to the pipeline as ``job.json``;
    resume re-uses it verbatim.
    """

    subject: str
    output_dir: str
    bids_dir: str | None = None
    derivatives_dir: str | None = None
    work_dir: str | None = None
    dataset: str = "unknown"
    task: str | None = None
    sessions: list[str] = field(default_factory=list)
    inputs: dict[str, Any] = field(default_factory=dict)   # extra pipeline inputs by name
    plugin: str = "Linear"
    n_procs: int | None = None
    use_cache: bool = True
    rerun_from: list[str] = field(default_factory=list)
    abort_on_bad: bool = False
    params_override: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PipelineRunRequest:
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})

    def resolve_input(self, name: str) -> Any:
        """Resolve a ``$inputs.<name>`` reference against this request.

        Built-in names map onto the request's own fields; anything else
        is looked up in ``inputs``.
        """
        builtin = {
            "subject": self.subject,
            "bids_dir": self.bids_dir,
            "derivatives_dir": self.derivatives_dir,
            "output_dir": self.output_dir,
            "work_dir": self.work_dir,
            "dataset": self.dataset,
            "task": self.task,
            "sessions": list(self.sessions),
        }
        if name in self.inputs:
            return self.inputs[name]
        if name in builtin:
            return builtin[name]
        raise KeyError(f"run request has no input named {name!r}")
