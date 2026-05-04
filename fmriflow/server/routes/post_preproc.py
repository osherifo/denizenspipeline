"""Post-preproc API: list nipype nodes, validate graphs, kick off runs."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from fmriflow.modules._schema import extract_schema
from fmriflow.post_preproc.graph import PostPreprocGraph
from fmriflow.post_preproc.manifest import PostPreprocConfig

router = APIRouter(tags=["post-preproc"])
logger = logging.getLogger(__name__)


class ValidateBody(BaseModel):
    graph: dict[str, Any]


class RunBody(BaseModel):
    subject: str
    source_manifest_path: str
    graph: dict[str, Any]
    output_dir: str
    name: str | None = None


class WorkflowSaveBody(BaseModel):
    name: str
    description: str = ""
    graph: dict[str, Any]
    inputs: dict[str, Any] = {}
    outputs: dict[str, Any] = {}


def _node_specs(registry):
    return registry._nipype_nodes


@router.get("/post-preproc/nodes")
async def list_nodes(request: Request):
    """Return all registered nipype-node modules with INPUTS/OUTPUTS/PARAM_SCHEMA."""
    registry = request.app.state.registry
    nodes = _node_specs(registry)
    out = []
    for name, cls in sorted(nodes.items()):
        out.append({
            "name": name,
            "docstring": (cls.__doc__ or "").strip().split("\n")[0],
            "inputs": list(getattr(cls, "INPUTS", [])),
            "outputs": list(getattr(cls, "OUTPUTS", [])),
            "params": extract_schema(cls),
        })
    return out


@router.post("/post-preproc/graphs/validate")
async def validate_graph(request: Request, body: ValidateBody):
    registry = request.app.state.registry
    g = PostPreprocGraph.from_reactflow(body.graph)
    errors = g.validate_against(_node_specs(registry))
    return {"valid": not errors, "errors": errors}


@router.post("/post-preproc/run")
async def start_run(request: Request, body: RunBody):
    registry = request.app.state.registry
    g = PostPreprocGraph.from_reactflow(body.graph)
    errors = g.validate_against(_node_specs(registry))
    if errors:
        raise HTTPException(400, {"errors": errors})

    cfg = PostPreprocConfig(
        subject=body.subject,
        source_manifest_path=body.source_manifest_path,
        graph=body.graph,
        output_dir=body.output_dir,
        name=body.name,
    )
    mgr = request.app.state.post_preproc_manager
    workflow_store = getattr(request.app.state, "post_preproc_workflow_store", None)
    handle = mgr.start(cfg, registry, workflow_store=workflow_store)
    return {
        "run_id": handle.run_id,
        "status": handle.status,
        "output_dir": handle.output_dir,
    }


@router.get("/post-preproc/runs/{run_id}")
async def get_run(request: Request, run_id: str):
    mgr = request.app.state.post_preproc_manager
    handle = mgr.get(run_id)
    if handle is None:
        raise HTTPException(404, f"Unknown run {run_id}")
    return {
        "run_id": handle.run_id,
        "status": handle.status,
        "error": handle.error,
        "output_dir": handle.output_dir,
        "manifest": handle.manifest,
    }


@router.get("/post-preproc/runs")
async def list_runs(request: Request):
    mgr = request.app.state.post_preproc_manager
    return [
        {
            "run_id": h.run_id,
            "status": h.status,
            "output_dir": h.output_dir,
            "subject": h.config.get("subject"),
        }
        for h in mgr.list()
    ]


@router.get("/post-preproc/manifests/{subject}")
async def get_manifest(request: Request, subject: str, output_dir: str):
    """Read a post_preproc_manifest.json from a given output_dir.

    The frontend passes the subject's output_dir explicitly so we don't
    need a global registry of post-preproc manifests yet.
    """
    p = Path(output_dir) / "post_preproc_manifest.json"
    if not p.is_file():
        raise HTTPException(404, f"No manifest at {p}")
    import json
    return json.loads(p.read_text())


# ── Saved workflows ─────────────────────────────────────────────────────


@router.get("/post-preproc/workflows")
async def list_workflows(request: Request):
    store = request.app.state.post_preproc_workflow_store
    return store.list()


@router.get("/post-preproc/workflows/{name}")
async def get_workflow(request: Request, name: str):
    store = request.app.state.post_preproc_workflow_store
    wf = store.get(name)
    if wf is None:
        raise HTTPException(404, f"No workflow {name!r}")
    return wf


@router.post("/post-preproc/workflows")
async def save_workflow(request: Request, body: WorkflowSaveBody):
    store = request.app.state.post_preproc_workflow_store
    path = store.save(
        body.name,
        body.graph,
        description=body.description,
        inputs=body.inputs,
        outputs=body.outputs,
    )
    return {"saved": True, "path": str(path), "name": body.name}


@router.delete("/post-preproc/workflows/{name}")
async def delete_workflow(request: Request, name: str):
    store = request.app.state.post_preproc_workflow_store
    if not store.delete(name):
        raise HTTPException(404, f"No workflow {name!r}")
    return {"deleted": True, "name": name}
