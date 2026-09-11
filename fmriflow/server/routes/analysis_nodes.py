"""Analysis node catalog: every module as a graph node type, plus port types."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from fmriflow.analysis.catalog import NodeCatalog
from fmriflow.analysis.port_types import describe as describe_port_types
from fmriflow.server.routes import _registry

router = APIRouter(tags=["analysis-nodes"])


def _catalog(request: Request) -> NodeCatalog:
    # Built per request from the shared registry, so modules registered or
    # edited at runtime appear without a restart.
    return NodeCatalog(_registry(request)).discover()


@router.get("/analysis/nodes")
async def list_analysis_nodes(request: Request, include_hidden: bool = False):
    catalog = _catalog(request)
    return {"nodes": [info.to_dict() for info in catalog.list(include_hidden=include_hidden)]}


@router.get("/analysis/port-types")
async def list_port_types():
    return {"types": describe_port_types()}


@router.get("/analysis/nodes/{node_type:path}")
async def get_analysis_node(request: Request, node_type: str):
    catalog = _catalog(request)
    if not catalog.has(node_type):
        raise HTTPException(status_code=404, detail=f"unknown analysis node type {node_type!r}")
    return catalog.info(node_type).to_dict()
