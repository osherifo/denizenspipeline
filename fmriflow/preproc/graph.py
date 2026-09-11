"""Pipeline graph — the one model for a preprocessing pipeline.

A preprocessing pipeline is a DAG of nodes drawn from the node library
(:mod:`fmriflow.preproc.node_registry`). fmriprep, a BIDS-app, a shell
command, a single transform, an imported nipype workflow and a
user-authored node are all just nodes here; the runner turns the whole
graph into one nipype ``Workflow``.

The model, topology and structural validation come from the shared graph
core (:mod:`fmriflow.graph`); this module adds what is specific to
preprocessing: node kinds, ``iter`` (map a node over a list input),
pipeline-level ``checks``, and the ``manifest`` block.

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

from dataclasses import asdict, dataclass, field
from typing import Any, ClassVar, Literal

from fmriflow.graph.model import (  # noqa: F401  (re-exported)
    INPUT_REF_PREFIX,
    SCHEMA_VERSION,
    EdgeSpec,
    GraphSpec,
    NodeSpec,
)

NodeKind = Literal["interface", "container_app", "composite", "source"]
NODE_KINDS: tuple[str, ...] = ("interface", "container_app", "composite", "source")


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
class PipelineNode(NodeSpec):
    kind: str = "interface"         # NodeKind; validated against the library
    iter: dict[str, Any] | None = None    # {"handle": "<port>"} or {"handles": [...]} (+ optional literal "values")
    # Pipeline-level checkpoint entries: {step, artifact, metric, norms?, live?, enabled?}
    checks: list[dict[str, Any]] = field(default_factory=list)

    DEFAULT_KIND: ClassVar[str] = "interface"

    def data_to_dict(self) -> dict[str, Any]:
        data = super().data_to_dict()
        if self.iter is not None:
            data["iter"] = dict(self.iter)
        if self.checks:
            data["checks"] = [dict(c) for c in self.checks]
        return data

    @classmethod
    def data_from_dict(cls, data: dict[str, Any]) -> dict[str, Any]:
        out = super().data_from_dict(data)
        it = data.get("iter")
        out["iter"] = dict(it) if isinstance(it, dict) else None
        out["checks"] = [dict(c) for c in (data.get("checks") or []) if isinstance(c, dict)]
        return out


@dataclass
class PipelineEdge(EdgeSpec):
    source_handle: str = "out_file"
    target_handle: str = "in_file"

    DEFAULT_SOURCE_HANDLE: ClassVar[str] = "out_file"
    DEFAULT_TARGET_HANDLE: ClassVar[str] = "in_file"


@dataclass
class Pipeline(GraphSpec):
    nodes: list[PipelineNode] = field(default_factory=list)
    edges: list[PipelineEdge] = field(default_factory=list)
    manifest: dict[str, Any] = field(default_factory=dict)

    NODE_CLS: ClassVar[type] = PipelineNode
    EDGE_CLS: ClassVar[type] = PipelineEdge
    WRAPPER_KEY: ClassVar[str] = "pipeline"   # accept a `pipeline:` wrapper, like other stage configs
    NOUN: ClassVar[str] = "pipeline"
    CYCLE_MESSAGE: ClassVar[str] = "pipeline graph has a cycle"

    # ── serialisation ──────────────────────────────────────────────

    def _extra_to_dict(self) -> dict[str, Any]:
        return {"manifest": dict(self.manifest)}

    @classmethod
    def _extra_from_dict(cls, data: dict[str, Any]) -> dict[str, Any]:
        return {"manifest": dict(data.get("manifest") or {})}

    # ── validation ─────────────────────────────────────────────────

    def _node_errors(self, n: NodeSpec, registry: Any | None) -> list[str]:
        errors: list[str] = []
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
        return errors

    def _validate_extra(self, registry: Any | None) -> list[str]:
        errors: list[str] = []
        ids = {n.id for n in self.nodes}

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
                # The list to iterate over arrives on the handle's edge, is a
                # list literal on the port, or is given as ``values``.
                fed_by_edge = any(e.target_handle == handle for e in self.predecessors(n.id))
                literal = n.literal_inputs.get(handle)
                if handle in n.literal_inputs and not isinstance(literal, list):
                    errors.append(
                        f"node {n.id}: iter handle {handle!r} has a literal value that is not a list "
                        f"({literal!r}); give one item per iteration"
                    )
                elif not fed_by_edge and handle not in n.literal_inputs and "values" not in n.iter:
                    errors.append(
                        f"node {n.id}: iter handle {handle!r} needs an incoming edge, a list literal or 'values'"
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
