"""Endpoints behind the 'View graph' modal in the dashboard.

For a finished subject run:

  * ``GET  /api/runs/{run_id}/graph``
  * ``GET  /api/runs/{run_id}/node/{node_id}/source``
  * ``GET  /api/runs/{run_id}/node/{node_id}/outputs``
  * ``GET  /api/runs/{run_id}/node/{node_id}/file/{rel:path}``

For a finished group run:

  * ``GET  /api/group-runs/{name}/{run_id}/graph``
  * ``GET  /api/group-runs/{name}/{run_id}/node/{node_id}/source``
  * ``GET  /api/group-runs/{name}/{run_id}/node/{node_id}/outputs``
  * ``GET  /api/group-runs/{name}/{run_id}/subject/{sub}/graph``  (zoom-in)

A *node_id* uses the same scheme returned by
:func:`fmriflow.server.services.run_graph.build_subject_graph`: stage
nodes are ``stage:<key>``; plugin nodes are ``<stage_key>:<plugin_name>``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from fmriflow.core import paths
from fmriflow.server.services.run_graph import (
    GraphNode,
    build_group_graph,
    build_subject_graph,
    list_node_outputs,
    read_source,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["run-graph"])


# ── helpers ────────────────────────────────────────────────────────────


def _registry(request: Request):
    """Return the shared ModuleRegistry on app.state, building one if missing."""
    reg = getattr(request.app.state, 'registry', None)
    if reg is None:
        from fmriflow.registry import ModuleRegistry
        reg = ModuleRegistry()
        reg.discover()
        request.app.state.registry = reg
    return reg


def _find_run_or_404(request: Request, run_id: str) -> dict:
    store = request.app.state.run_store
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404,
                            detail=f"Run '{run_id}' not found")
    return run


def _resolve_group_run_dir(group_name: str, run_id: str) -> Path:
    """Return the on-disk dir for a group run, or raise 404.

    Mirrors the resolution logic in :mod:`routes.group` (kept local so
    the two route files stay decoupled).
    """
    if not group_name or '/' in group_name or group_name.startswith('.'):
        raise HTTPException(status_code=400, detail="invalid group name")
    if not run_id or '/' in run_id or run_id.startswith('.'):
        raise HTTPException(status_code=400, detail="invalid run_id")
    base = paths.group_runs_root() / group_name / run_id
    if not (base / 'group_summary.json').is_file():
        raise HTTPException(
            status_code=404,
            detail=f"group_summary.json not found at {base}")
    return base


def _read_group_summary(run_dir: Path) -> dict:
    return json.loads((run_dir / 'group_summary.json').read_text())


def _find_node(graph: dict, node_id: str) -> dict:
    for n in graph.get('nodes', []):
        if n.get('id') == node_id:
            return n
    raise HTTPException(status_code=404,
                        detail=f"Node '{node_id}' not in graph")


def _safe_join(base: Path, rel: str) -> Path:
    """Resolve ``rel`` under ``base``, refusing path escapes."""
    if not rel or rel.startswith('/'):
        raise HTTPException(status_code=400, detail="invalid file path")
    parts = rel.split('/')
    if any(p in ('', '..') or p.startswith('.') for p in parts):
        raise HTTPException(status_code=400, detail="invalid file path")
    full = (base / rel).resolve(strict=False)
    base_resolved = base.resolve(strict=False)
    if not (str(full) == str(base_resolved)
            or str(full).startswith(str(base_resolved) + '/')):
        raise HTTPException(status_code=400, detail="path escapes run dir")
    if not full.is_file():
        raise HTTPException(status_code=404, detail=f"not a file: {rel}")
    return full


def _serve_source(source_path: str) -> dict:
    """Read a plugin source file and wrap it for JSON response."""
    p = Path(source_path)
    if not p.is_file():
        raise HTTPException(
            status_code=404, detail=f"source file not found: {source_path}")
    try:
        text = read_source(str(p))
    except Exception as exc:
        raise HTTPException(status_code=500,
                            detail=f"could not read source: {exc}") from exc
    return {
        'path': str(p),
        'language': 'python' if p.suffix == '.py' else 'text',
        'text': text,
        'size': p.stat().st_size,
    }


# ── subject run ────────────────────────────────────────────────────────


@router.get("/runs/{run_id}/graph")
async def subject_run_graph(request: Request, run_id: str):
    run = _find_run_or_404(request, run_id)
    summary = run['summary']
    graph = build_subject_graph(
        summary.config_snapshot,
        [s.__dict__ if hasattr(s, '__dict__') else s for s in summary.stages],
        _registry(request),
    )
    return {
        'run_id': run_id,
        'experiment': summary.experiment,
        'subject': summary.subject,
        'output_dir': run['output_dir'],
        **graph.to_dict(),
    }


@router.get("/runs/{run_id}/node/{node_id:path}/source")
async def subject_node_source(request: Request, run_id: str, node_id: str):
    run = _find_run_or_404(request, run_id)
    summary = run['summary']
    graph = build_subject_graph(
        summary.config_snapshot,
        [s.__dict__ if hasattr(s, '__dict__') else s for s in summary.stages],
        _registry(request),
    ).to_dict()
    node = _find_node(graph, node_id)
    if not node.get('source_path'):
        raise HTTPException(
            status_code=404,
            detail=f"No source registered for node '{node_id}'",
        )
    return _serve_source(node['source_path'])


@router.get("/runs/{run_id}/node/{node_id:path}/outputs")
async def subject_node_outputs(request: Request, run_id: str, node_id: str):
    run = _find_run_or_404(request, run_id)
    summary = run['summary']
    graph = build_subject_graph(
        summary.config_snapshot,
        [s.__dict__ if hasattr(s, '__dict__') else s for s in summary.stages],
        _registry(request),
    ).to_dict()
    node = _find_node(graph, node_id)
    output_dir = Path(run['output_dir'])
    files = list_node_outputs(output_dir, GraphNode(**{
        k: v for k, v in node.items() if k in GraphNode.__dataclass_fields__
    }))
    return {
        'node_id': node_id,
        'output_dir': str(output_dir),
        'files': files,
    }


@router.get("/runs/{run_id}/node/{node_id:path}/file/{rel:path}")
async def subject_node_file(request: Request, run_id: str,
                            node_id: str, rel: str):
    run = _find_run_or_404(request, run_id)
    output_dir = Path(run['output_dir'])
    full = _safe_join(output_dir, rel)
    return FileResponse(str(full))


# ── group run ──────────────────────────────────────────────────────────


@router.get("/group-runs/{name}/{run_id}/graph")
async def group_run_graph(request: Request, name: str, run_id: str):
    run_dir = _resolve_group_run_dir(name, run_id)
    summary = _read_group_summary(run_dir)
    graph = build_group_graph(summary, _registry(request))
    return {
        'group_name': summary.get('group_name', name),
        'run_id': run_id,
        'output_dir': str(run_dir),
        **graph.to_dict(),
    }


@router.get("/group-runs/{name}/{run_id}/node/{node_id:path}/source")
async def group_node_source(request: Request, name: str, run_id: str,
                            node_id: str):
    run_dir = _resolve_group_run_dir(name, run_id)
    summary = _read_group_summary(run_dir)
    graph = build_group_graph(summary, _registry(request)).to_dict()
    node = _find_node(graph, node_id)
    if not node.get('source_path'):
        raise HTTPException(
            status_code=404,
            detail=f"No source registered for node '{node_id}'",
        )
    return _serve_source(node['source_path'])


@router.get("/group-runs/{name}/{run_id}/node/{node_id:path}/outputs")
async def group_node_outputs(request: Request, name: str, run_id: str,
                             node_id: str):
    run_dir = _resolve_group_run_dir(name, run_id)
    summary = _read_group_summary(run_dir)
    graph = build_group_graph(summary, _registry(request)).to_dict()
    node = _find_node(graph, node_id)
    files = list_node_outputs(run_dir, GraphNode(**{
        k: v for k, v in node.items() if k in GraphNode.__dataclass_fields__
    }))
    return {
        'node_id': node_id,
        'output_dir': str(run_dir),
        'files': files,
    }


@router.get("/group-runs/{name}/{run_id}/node/{node_id:path}/file/{rel:path}")
async def group_node_file(name: str, run_id: str, node_id: str, rel: str):
    run_dir = _resolve_group_run_dir(name, run_id)
    full = _safe_join(run_dir, rel)
    return FileResponse(str(full))


@router.get("/group-runs/{name}/{run_id}/subject/{sub}/graph")
async def group_subject_graph(request: Request, name: str, run_id: str,
                              sub: str):
    """Zoom-in: the 7-stage subject graph for one subject of a group run."""
    run_dir = _resolve_group_run_dir(name, run_id)
    summary = _read_group_summary(run_dir)
    for s in summary.get('subject_summaries') or []:
        if s.get('subject') == sub:
            graph = build_subject_graph(
                s.get('config_snapshot') or {},
                s.get('stages') or [],
                _registry(request),
            )
            sub_dir = run_dir / 'subjects' / sub
            return {
                'run_id': run_id,
                'group_name': summary.get('group_name', name),
                'subject': sub,
                'experiment': s.get('experiment', ''),
                'output_dir': str(sub_dir),
                **graph.to_dict(),
            }
    raise HTTPException(
        status_code=404,
        detail=f"subject '{sub}' not found in group run {name}/{run_id}",
    )


@router.get("/group-runs/{name}/{run_id}/subject/{sub}/node/{node_id:path}/outputs")
async def group_subject_node_outputs(request: Request, name: str, run_id: str,
                                     sub: str, node_id: str):
    run_dir = _resolve_group_run_dir(name, run_id)
    summary = _read_group_summary(run_dir)
    for s in summary.get('subject_summaries') or []:
        if s.get('subject') == sub:
            graph = build_subject_graph(
                s.get('config_snapshot') or {},
                s.get('stages') or [],
                _registry(request),
            ).to_dict()
            node = _find_node(graph, node_id)
            sub_dir = run_dir / 'subjects' / sub
            files = list_node_outputs(sub_dir, GraphNode(**{
                k: v for k, v in node.items()
                if k in GraphNode.__dataclass_fields__
            }))
            return {
                'node_id': node_id,
                'output_dir': str(sub_dir),
                'files': files,
            }
    raise HTTPException(
        status_code=404,
        detail=f"subject '{sub}' not found in group run {name}/{run_id}",
    )


@router.get("/group-runs/{name}/{run_id}/subject/{sub}/node/{node_id:path}/source")
async def group_subject_node_source(request: Request, name: str, run_id: str,
                                    sub: str, node_id: str):
    run_dir = _resolve_group_run_dir(name, run_id)
    summary = _read_group_summary(run_dir)
    for s in summary.get('subject_summaries') or []:
        if s.get('subject') == sub:
            graph = build_subject_graph(
                s.get('config_snapshot') or {},
                s.get('stages') or [],
                _registry(request),
            ).to_dict()
            node = _find_node(graph, node_id)
            if not node.get('source_path'):
                raise HTTPException(
                    status_code=404,
                    detail=f"No source registered for node '{node_id}'",
                )
            return _serve_source(node['source_path'])
    raise HTTPException(
        status_code=404,
        detail=f"subject '{sub}' not found in group run {name}/{run_id}",
    )


@router.get("/group-runs/{name}/{run_id}/subject/{sub}/node/{node_id:path}/file/{rel:path}")
async def group_subject_node_file(name: str, run_id: str, sub: str,
                                  node_id: str, rel: str):
    run_dir = _resolve_group_run_dir(name, run_id)
    sub_dir = run_dir / 'subjects' / sub
    if not sub_dir.is_dir():
        raise HTTPException(status_code=404,
                            detail=f"subject dir not found: {sub}")
    full = _safe_join(sub_dir, rel)
    return FileResponse(str(full))
