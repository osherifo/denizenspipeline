"""Execute a post-preproc graph against a PreprocManifest.

The runner supports three node-shape special cases on top of plain
"call instance.run()" execution:

- **preproc_run**: source node that resolves a path from the upstream
  PreprocManifest by ``run_name``.
- **subworkflow**: opaque node that loads a saved workflow YAML and runs
  it as a nested ``_run_graph`` call with wired-through inputs/outputs.
- **_iter**: a node that iterates over a list of values for a given
  input handle. Iterating nodes are sinks (no outgoing edges) in v1.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from fmriflow.post_preproc.graph import PostPreprocGraph
from fmriflow.post_preproc.manifest import (
    NodeRunRecord,
    PostPreprocConfig,
    PostPreprocManifest,
)
from fmriflow.preproc.manifest import PreprocManifest

logger = logging.getLogger(__name__)


def _resolve_source_run(
    source_manifest: PreprocManifest, run_name: str
) -> str:
    for r in source_manifest.runs:
        if r.run_name == run_name:
            return str(Path(source_manifest.output_dir) / r.output_file)
    raise ValueError(
        f"run_name {run_name!r} not in source manifest "
        f"(have {[r.run_name for r in source_manifest.runs]})"
    )


def _all_source_run_paths(source_manifest: PreprocManifest) -> list[str]:
    return [
        str(Path(source_manifest.output_dir) / r.output_file)
        for r in source_manifest.runs
    ]


def _build_node_inputs(
    graph: PostPreprocGraph,
    node,
    node_out: dict[str, dict[str, Path]],
    extra_inputs: dict[str, Path] | None,
) -> dict[str, Path]:
    """Resolve a node's input-handle map from edges, then `_inputs`, then
    caller-supplied ``extra_inputs`` (subworkflow pass-through).

    Precedence: incoming edge > caller extra_inputs > params._inputs.
    """
    inputs: dict[str, Path] = {}
    for edge in graph.predecessors(node.id):
        src_outputs = node_out.get(edge.source, {})
        if edge.source_handle not in src_outputs:
            raise RuntimeError(
                f"Node {node.id}: predecessor {edge.source} missing "
                f"output {edge.source_handle!r}"
            )
        inputs[edge.target_handle] = src_outputs[edge.source_handle]

    if extra_inputs:
        for handle, path in extra_inputs.items():
            inputs.setdefault(handle, Path(path) if not isinstance(path, Path) else path)

    literal_inputs = node.params.get("_inputs") or {}
    if isinstance(literal_inputs, dict):
        for handle, path in literal_inputs.items():
            if handle in inputs or not path:
                continue
            inputs[handle] = Path(path)

    return inputs


def _run_graph(
    graph_data: dict[str, Any],
    *,
    source_manifest: PreprocManifest,
    out_root: Path,
    registry,
    workflow_stack: tuple[str, ...] = (),
    workflow_store=None,
    extra_inputs_per_node: dict[str, dict[str, Path]] | None = None,
) -> tuple[list[NodeRunRecord], dict[str, dict[str, Any]]]:
    """Run a graph; return (per-node records, node_out map).

    ``node_out[node_id][handle]`` is a Path for ordinary outputs and a
    ``list[Path]`` for nodes that ran with ``_iter``.
    """
    graph = PostPreprocGraph.from_reactflow(graph_data)
    out_root.mkdir(parents=True, exist_ok=True)
    extra_inputs_per_node = extra_inputs_per_node or {}

    node_out: dict[str, dict[str, Any]] = {}
    runs: list[NodeRunRecord] = []

    for node in graph.topo_order():
        node_dir = out_root / node.id
        params: dict[str, Any] = dict(node.params)
        extra = extra_inputs_per_node.get(node.id) or {}

        # Iteration shortcut: collect values, run N times, accumulate lists.
        iter_spec = params.get("_iter") if isinstance(params.get("_iter"), dict) else None

        if node.type == "subworkflow":
            outputs, record = _run_subworkflow_node(
                node=node,
                params=params,
                inputs=_build_node_inputs(graph, node, node_out, extra),
                out_dir=node_dir,
                source_manifest=source_manifest,
                registry=registry,
                workflow_store=workflow_store,
                workflow_stack=workflow_stack,
            )
            node_out[node.id] = outputs
            runs.append(record)
            continue

        if iter_spec:
            outputs, record = _run_iterating_node(
                node=node,
                params=params,
                graph=graph,
                node_out=node_out,
                extra=extra,
                out_dir=node_dir,
                registry=registry,
                source_manifest=source_manifest,
                iter_spec=iter_spec,
            )
            node_out[node.id] = outputs
            runs.append(record)
            continue

        # Normal node.
        cls = registry.get_module_class("nipype_nodes", node.type)
        instance = cls()
        inputs = _build_node_inputs(graph, node, node_out, extra)

        if node.type == "preproc_run":
            params["_resolved_path"] = _resolve_source_run(
                source_manifest, params.get("run_name") or ""
            )

        t0 = time.time()
        outputs = instance.run(inputs, node_dir, params)
        elapsed = time.time() - t0

        outputs_str = {k: str(v) for k, v in outputs.items()}
        node_out[node.id] = {k: Path(v) for k, v in outputs_str.items()}

        runs.append(
            NodeRunRecord(
                node_id=node.id,
                node_type=node.type,
                params={k: v for k, v in node.params.items()},
                inputs={k: str(v) for k, v in inputs.items()},
                outputs=outputs_str,
                duration_s=elapsed,
            )
        )

    return runs, node_out


def _run_iterating_node(
    *,
    node,
    params: dict[str, Any],
    graph: PostPreprocGraph,
    node_out: dict[str, dict[str, Any]],
    extra: dict[str, Path],
    out_dir: Path,
    registry,
    source_manifest: PreprocManifest,
    iter_spec: dict[str, Any],
) -> tuple[dict[str, list[str]], NodeRunRecord]:
    """Run an iterating node once per value; collect outputs into lists."""
    handle = iter_spec.get("handle") or "in_file"
    values: list[str]
    if iter_spec.get("from_source_manifest"):
        values = _all_source_run_paths(source_manifest)
    else:
        raw = iter_spec.get("values") or []
        values = [str(v) for v in raw]

    if not values:
        raise ValueError(
            f"Iterating node {node.id}: _iter has no values to iterate over"
        )

    cls = registry.get_module_class("nipype_nodes", node.type)
    instance = cls()
    base_inputs = _build_node_inputs(graph, node, node_out, extra)
    if handle in base_inputs:
        raise ValueError(
            f"Iterating node {node.id}: handle {handle!r} is also wired or "
            f"set via _inputs; remove the wire/literal or the iteration."
        )

    # Iterating nodes must be sinks in v1 (no outgoing edges).
    has_out = any(e.source == node.id for e in graph.edges)
    if has_out:
        raise ValueError(
            f"Iterating node {node.id}: outgoing edges aren't supported "
            f"yet. Use a literal sink for v1."
        )

    collected: dict[str, list[str]] = {}
    iter_inputs_record: list[dict[str, str]] = []

    t0 = time.time()
    for i, value in enumerate(values):
        per_dir = out_dir / f"{i:03d}"
        inputs = dict(base_inputs)
        inputs[handle] = Path(value)
        per_params = dict(params)

        if node.type == "preproc_run":
            per_params["_resolved_path"] = value

        outputs = instance.run(inputs, per_dir, per_params)
        for k, v in outputs.items():
            collected.setdefault(k, []).append(str(v))
        iter_inputs_record.append({handle: str(value)})
    elapsed = time.time() - t0

    record = NodeRunRecord(
        node_id=node.id,
        node_type=node.type,
        params={k: v for k, v in node.params.items()},
        inputs={"_iter_handle": handle, "_iter_count": str(len(values))},
        outputs={k: ",".join(v) for k, v in collected.items()},
        duration_s=elapsed,
    )
    # Internally we keep the lists as the node's output shape.
    return ({k: v for k, v in collected.items()}, record)  # type: ignore[return-value]


def _run_subworkflow_node(
    *,
    node,
    params: dict[str, Any],
    inputs: dict[str, Path],
    out_dir: Path,
    source_manifest: PreprocManifest,
    registry,
    workflow_store,
    workflow_stack: tuple[str, ...],
) -> tuple[dict[str, Path], NodeRunRecord]:
    name = params.get("workflow_name")
    if not name:
        raise ValueError(f"subworkflow {node.id}: missing workflow_name")
    if workflow_store is None:
        raise RuntimeError(
            "subworkflow execution requires a workflow store; the runner "
            "wasn't given one"
        )
    if name in workflow_stack:
        raise RuntimeError(
            f"subworkflow cycle: {' -> '.join(workflow_stack + (name,))}"
        )
    wf = workflow_store.get(name)
    if wf is None:
        raise FileNotFoundError(f"subworkflow {node.id}: workflow {name!r} not found")

    inputs_map = wf.get("inputs") or {}
    outputs_map = wf.get("outputs") or {}
    inner_graph = wf.get("graph") or {"nodes": [], "edges": []}

    # Build per-inner-node extra_inputs from the workflow's `inputs:` mapping
    # plus the wrapper's incoming `inputs`.
    extra_inputs_per_node: dict[str, dict[str, Path]] = {}
    for wf_handle, target_path in inputs_map.items():
        if wf_handle not in inputs:
            continue
        spec = target_path or {}
        from_str = spec.get("from") if isinstance(spec, dict) else str(spec)
        if not from_str or "." not in from_str:
            raise ValueError(
                f"subworkflow {name}: input {wf_handle!r} has bad target {spec!r}"
            )
        inner_id, inner_handle = from_str.split(".", 1)
        extra_inputs_per_node.setdefault(inner_id, {})[inner_handle] = inputs[wf_handle]

    inner_runs, inner_node_out = _run_graph(
        inner_graph,
        source_manifest=source_manifest,
        out_root=out_dir,
        registry=registry,
        workflow_stack=workflow_stack + (name,),
        workflow_store=workflow_store,
        extra_inputs_per_node=extra_inputs_per_node,
    )

    # Map inner node outputs back up to the wrapper's declared outputs.
    outputs: dict[str, Path] = {}
    for wf_out, target in outputs_map.items():
        spec = target or {}
        from_str = spec.get("from") if isinstance(spec, dict) else str(spec)
        if not from_str or "." not in from_str:
            raise ValueError(
                f"subworkflow {name}: output {wf_out!r} has bad source {spec!r}"
            )
        inner_id, inner_handle = from_str.split(".", 1)
        produced = inner_node_out.get(inner_id, {}).get(inner_handle)
        if produced is None:
            raise RuntimeError(
                f"subworkflow {name}: inner node {inner_id} did not produce "
                f"output {inner_handle!r}"
            )
        # If iteration produced a list, take the first; v1 simplification.
        outputs[wf_out] = (
            Path(produced[0]) if isinstance(produced, list) and produced
            else Path(produced)
        )

    record = NodeRunRecord(
        node_id=node.id,
        node_type="subworkflow",
        params={k: v for k, v in node.params.items()},
        inputs={k: str(v) for k, v in inputs.items()},
        outputs={k: str(v) for k, v in outputs.items()},
        duration_s=sum((r.duration_s or 0.0) for r in inner_runs),
    )
    return outputs, record


def run_post_preproc(
    config: PostPreprocConfig,
    *,
    registry,
    workflow_store=None,
) -> PostPreprocManifest:
    """Top-level entry point. Executes ``config.graph`` and writes a manifest."""
    source_manifest = PreprocManifest.from_json(config.source_manifest_path)
    out_root = Path(config.output_dir)
    runs, _ = _run_graph(
        config.graph,
        source_manifest=source_manifest,
        out_root=out_root,
        registry=registry,
        workflow_store=workflow_store,
    )
    manifest = PostPreprocManifest(
        subject=config.subject,
        dataset=source_manifest.dataset,
        source_manifest_path=str(config.source_manifest_path),
        graph=config.graph,
        nodes_run=runs,
        output_dir=str(out_root),
    )
    manifest.save(out_root / "post_preproc_manifest.json")
    return manifest
