"""Execute a post-preproc graph against a PreprocManifest."""

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
    """Find run_name in the source manifest; return absolute output_file path."""
    for r in source_manifest.runs:
        if r.run_name == run_name:
            return str(Path(source_manifest.output_dir) / r.output_file)
    raise ValueError(
        f"run_name {run_name!r} not in source manifest "
        f"(have {[r.run_name for r in source_manifest.runs]})"
    )


def run_post_preproc(
    config: PostPreprocConfig,
    *,
    registry,
) -> PostPreprocManifest:
    """Execute the graph in ``config`` and write a PostPreprocManifest."""
    source_manifest = PreprocManifest.from_json(config.source_manifest_path)
    graph = PostPreprocGraph.from_reactflow(config.graph)
    out_root = Path(config.output_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    # Per-node output dir under out_root.
    node_out: dict[str, dict[str, Path]] = {}
    runs: list[NodeRunRecord] = []

    for node in graph.topo_order():
        cls = registry.get_module_class("nipype_nodes", node.type)
        instance = cls()

        # Build inputs from incoming edges.
        inputs: dict[str, Path] = {}
        for edge in graph.predecessors(node.id):
            src_outputs = node_out.get(edge.source, {})
            if edge.source_handle not in src_outputs:
                raise RuntimeError(
                    f"Node {node.id}: predecessor {edge.source} missing "
                    f"output {edge.source_handle!r}"
                )
            inputs[edge.target_handle] = src_outputs[edge.source_handle]

        # Literal-path overrides for inputs without an edge: ``params._inputs``
        # is a {handle: "/path/to/file"} map set from the UI's input fields.
        literal_inputs = node.params.get("_inputs") or {}
        if isinstance(literal_inputs, dict):
            for handle, path in literal_inputs.items():
                if handle in inputs:
                    continue  # an edge wins over a literal path
                if path:
                    inputs[handle] = Path(path)

        # Source nodes resolve from the source manifest.
        params: dict[str, Any] = dict(node.params)
        if node.type == "preproc_run":
            run_name = params.get("run_name") or ""
            params["_resolved_path"] = _resolve_source_run(
                source_manifest, run_name
            )

        node_dir = out_root / node.id
        t0 = time.time()
        outputs = instance.run(inputs, node_dir, params)
        elapsed = time.time() - t0

        # Stringify for serialization.
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
