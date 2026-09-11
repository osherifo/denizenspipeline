"""Analysis graphs: templates, saved graphs (CRUD), validation, compilation and launch."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from fmriflow.analysis.catalog import NodeCatalog
from fmriflow.analysis.executor import check_graph
from fmriflow.analysis.graph import AnalysisGraph
from fmriflow.analysis.templates import (
    concrete_path_warnings, delete_user_template, list_templates, load_template, save_user_template,
)
from fmriflow.exceptions import ConfigError
from fmriflow.server.routes import _registry

router = APIRouter(tags=["analysis-graphs"])


class GraphBody(BaseModel):
    graph: dict[str, Any]
    inputs: dict[str, Any] = {}


class TemplateBody(BaseModel):
    name: str
    graph: dict[str, Any]


class CompileBody(BaseModel):
    """A stage config to compile: a saved config's filename *or* an inline config."""

    filename: str | None = None
    config: dict[str, Any] | None = None


class RunBody(BaseModel):
    """Launch: an inline graph *or* a saved graph's name, plus input values."""

    graph: dict[str, Any] | None = None
    graph_name: str | None = None
    inputs: dict[str, Any] = {}
    overrides: dict[str, Any] = {}


def _parse(data: dict[str, Any]) -> AnalysisGraph:
    try:
        return AnalysisGraph.from_dict(AnalysisGraph.unwrap(data))
    except Exception as e:
        raise HTTPException(400, detail=f"invalid graph: {e}")


def _catalog(request: Request) -> NodeCatalog:
    return NodeCatalog(_registry(request)).discover()


def _store(request: Request):
    return request.app.state.analysis_graph_store


def _errors(exc: Exception) -> str:
    return "; ".join(getattr(exc, "errors", None) or [str(exc)])


@router.get("/analysis/graphs")
async def list_graphs(request: Request):
    store = _store(request)
    return {"graphs": store.list_graphs(), "root": str(store.root)}


@router.get("/analysis/graphs/templates")
async def graph_templates():
    return {"templates": list_templates()}


@router.get("/analysis/graphs/templates/{name}")
async def graph_template(name: str):
    try:
        return {"graph": load_template(name).to_dict()}
    except KeyError as e:
        raise HTTPException(404, detail=str(e))


@router.post("/analysis/graphs/templates")
async def save_template(request: Request, body: TemplateBody):
    """Save the builder's graph as a user template (run panel dropped).

    ``warnings`` lists node values holding a concrete path, which will not
    travel to another dataset; ``errors`` is the structural validation.
    """
    graph = _parse(body.graph)
    errors = graph.validate(_catalog(request))
    warnings = concrete_path_warnings(graph)
    try:
        path = save_user_template(body.name, graph)
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
    return {"saved": True, "name": body.name, "tier": "user", "path": str(path),
            "warnings": warnings, "errors": errors}


@router.delete("/analysis/graphs/templates/{name}")
async def delete_template(name: str):
    try:
        deleted = delete_user_template(name)
    except ValueError as e:
        raise HTTPException(403, detail=str(e))
    if not deleted:
        raise HTTPException(404, detail=f"no user template named {name!r}")
    return {"deleted": True}


@router.post("/analysis/graphs/validate")
async def validate_graph(request: Request, body: GraphBody):
    """Everything that would stop the graph running with these inputs."""
    graph = _parse(body.graph)
    errors = check_graph(graph, _catalog(request), body.inputs)
    return {"ok": not errors, "errors": errors}


@router.post("/analysis/graphs/compile")
async def compile_config(request: Request, body: CompileBody):
    """Compile a stage-section subject config into the equivalent graph."""
    from fmriflow.analysis.compile_legacy import compile_subject_config
    from fmriflow.config.loader import load_config

    if body.filename:
        path = request.app.state.config_store._resolve_path(body.filename)
        if path is None:
            raise HTTPException(404, detail=f"config {body.filename!r} not found")
        raw = yaml.safe_load(Path(path).read_text()) or {}
        name = Path(body.filename).stem
    elif body.config is not None:
        raw, path, name = body.config, None, None
    else:
        raise HTTPException(400, detail="give either 'filename' or 'config'")
    if isinstance(raw, dict) and ("nodes" in AnalysisGraph.unwrap(raw)):
        raise HTTPException(400, detail="this is already a graph")
    if isinstance(raw, dict) and (isinstance(raw.get("study"), str) or isinstance(raw.get("group"), str)):
        raise HTTPException(400, detail="only subject configs compile to graphs so far")

    tmp_path = None
    try:
        if path is None:
            with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as tmp:
                yaml.safe_dump(raw, tmp, sort_keys=False)
                tmp_path = tmp.name
        config = load_config(path or tmp_path)
        graph = compile_subject_config(config, name=name)
    except Exception as e:
        raise HTTPException(400, detail=_errors(e))
    finally:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)
    return {"graph": graph.to_dict()}


@router.post("/analysis/graphs/run")
async def run_graph(request: Request, body: RunBody):
    manager = request.app.state.run_manager
    if body.graph is not None:
        doc, source = _parse(body.graph).to_dict(), body.graph_name or "inline graph"
    elif body.graph_name:
        try:
            doc, source = _store(request).load(body.graph_name).to_dict(), body.graph_name
        except KeyError as e:
            raise HTTPException(404, detail=str(e))
        except ValueError as e:
            raise HTTPException(400, detail=str(e))
    else:
        raise HTTPException(400, detail="give either 'graph' or 'graph_name'")
    try:
        run_id = manager.start_graph_run(doc, inputs=body.inputs, overrides=body.overrides, source=source)
    except (ValueError, ConfigError) as e:
        raise HTTPException(400, detail=_errors(e))
    return {"run_id": run_id, "status": "started"}


@router.get("/analysis/graphs/{name}")
async def get_graph(request: Request, name: str):
    store = _store(request)
    try:
        graph = store.load(name)
    except KeyError as e:
        raise HTTPException(404, detail=str(e))
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
    return {"name": name, "graph": graph.to_dict(), "path": str(store.root / f"{name}.yaml")}


@router.put("/analysis/graphs/{name}")
async def save_graph(request: Request, name: str, body: GraphBody):
    """Save a graph (saved even when invalid, like a pipeline; ``errors`` says what is wrong)."""
    store = _store(request)
    graph = _parse(body.graph)
    errors = graph.validate(_catalog(request))
    try:
        path = store.save(name, graph)
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
    config_store = getattr(request.app.state, "config_store", None)
    if config_store is not None:
        config_store._last_scan = 0.0
    return {"saved": True, "name": name, "path": str(path), "errors": errors}


@router.delete("/analysis/graphs/{name}")
async def delete_graph(request: Request, name: str):
    store = _store(request)
    try:
        deleted = store.delete(name)
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
    if not deleted:
        raise HTTPException(404, detail=f"no analysis graph named {name!r}")
    config_store = getattr(request.app.state, "config_store", None)
    if config_store is not None:
        config_store._last_scan = 0.0
    return {"deleted": True}
