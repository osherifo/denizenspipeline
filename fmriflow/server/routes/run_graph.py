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
    build_study_graph,
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


def _resolve_study_run_dir(study_name: str, run_id: str) -> Path:
    if not study_name or '/' in study_name or study_name.startswith('.'):
        raise HTTPException(status_code=400, detail="invalid study name")
    if not run_id or '/' in run_id or run_id.startswith('.'):
        raise HTTPException(status_code=400, detail="invalid run_id")
    base = paths.study_runs_root() / study_name / run_id
    if not (base / 'study_summary.json').is_file():
        raise HTTPException(
            status_code=404,
            detail=f"study_summary.json not found at {base}")
    return base


def _read_study_summary(run_dir: Path) -> dict:
    return json.loads((run_dir / 'study_summary.json').read_text())


def _resolve_study_group_run_dir(study_run_dir: Path, group_label: str) -> Path:
    """Find the group's timestamped subdir inside a study run.

    Study layout: ``<study_dir>/<run_id>/groups/<label>/<group_run_id>/``.
    Returns the newest matching group_run_id subdir (only one per
    invocation — StudyOrchestrator passes a deterministic run_id, so
    "newest" only picks something else if the user re-ran out of band).
    """
    if not group_label or '/' in group_label or group_label.startswith('.'):
        raise HTTPException(status_code=400, detail="invalid group_label")
    base = study_run_dir / 'groups' / group_label
    if not base.is_dir():
        raise HTTPException(
            status_code=404,
            detail=f"group '{group_label}' not in this study run")
    candidates = [
        p for p in base.iterdir()
        if p.is_dir() and p.name != 'latest'
        and (p / 'group_summary.json').is_file()
    ]
    if not candidates:
        raise HTTPException(
            status_code=404,
            detail=f"no group_summary.json for '{group_label}'")
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def _find_node(graph: dict, node_id: str) -> dict:
    for n in graph.get('nodes', []):
        if n.get('id') == node_id:
            return n
    # Helpful diagnostic — list the IDs actually present so 404s in
    # the wild are actionable instead of a wall.
    ids = [n.get('id') for n in graph.get('nodes', [])]
    raise HTTPException(
        status_code=404,
        detail=(
            f"Node '{node_id}' not in graph. "
            f"Available ids: {ids}"
        ),
    )


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


# ── in-flight synthesis ────────────────────────────────────────────────


def _stage_for_node_id(node_id: str) -> str | None:
    """``features:english1000`` → ``features``."""
    if not node_id or ':' not in node_id:
        return None
    return node_id.split(':', 1)[0]


def _fold_node_events(stages: dict[str, dict], events: list[dict],
                      *, subject_filter: str | None = None) -> None:
    """Fold ``node_start`` / ``node_done`` / ``node_fail`` events into the
    relevant StageRecord's ``nodes`` list, so ``_merge_recorded`` can
    overlay per-plugin status on top of the config-derived skeleton.

    ``subject_filter`` restricts to events tagged with that subject,
    used when synthesizing a single subject's stage table inside a
    group/study run.
    """
    by_node_id: dict[tuple[str, str], dict] = {}  # (stage, node_id) → rec
    for ev in events:
        e = ev.get('event')
        if e not in ('node_start', 'node_done', 'node_fail'):
            continue
        if subject_filter is not None and ev.get('subject') != subject_filter:
            continue
        node_id = ev.get('node_id') or ''
        stage = _stage_for_node_id(node_id)
        if not stage:
            continue
        key = (stage, node_id)
        rec = by_node_id.setdefault(key, {
            'id': node_id,
            'kind': ev.get('kind') or '',
            'name': ev.get('name') or '',
            'status': 'running',
            'elapsed_s': 0.0,
            'detail': '',
            'outputs': [],
        })
        if e == 'node_start':
            rec['status'] = 'running'
        elif e == 'node_done':
            rec['status'] = 'ok'
            rec['elapsed_s'] = ev.get('elapsed', 0.0) or 0.0
            rec['detail'] = ev.get('detail', '') or ''
        elif e == 'node_fail':
            rec['status'] = 'failed'
            rec['elapsed_s'] = ev.get('elapsed', 0.0) or 0.0
            rec['detail'] = ev.get('error', '') or ''

    for (stage, _), rec in by_node_id.items():
        stage_rec = stages.setdefault(stage, {
            'name': stage, 'status': 'running',
            'elapsed_s': 0.0, 'detail': '', 'nodes': [],
        })
        stage_rec.setdefault('nodes', []).append(rec)


def _events_to_subject_stages(events: list[dict],
                              *, subject_filter: str | None = None) -> list[dict]:
    """Project a stream of stage_start/done/fail (+ node_*) events to
    StageRecord-shaped dicts.

    Used for subject runs that haven't finished yet — no run_summary
    on disk, just the in-memory ``handle.events`` to read from. Status
    is 'running' for stages with a start but no done, 'ok'/'failed'/
    'warning' once a terminal event arrives. Each stage's nodes list
    is folded from any ``node_*`` events the orchestrator emitted in
    its ``_record`` context manager.
    """
    by_stage: dict[str, dict] = {}
    for ev in events:
        e = ev.get('event')
        stage = ev.get('stage')
        if subject_filter is not None and ev.get('subject') != subject_filter:
            continue
        if not stage or e not in (
            'stage_start', 'stage_done', 'stage_fail', 'stage_warn'
        ):
            continue
        rec = by_stage.setdefault(stage, {
            'name': stage, 'status': 'running',
            'elapsed_s': 0.0, 'detail': '', 'nodes': [],
        })
        if e == 'stage_start':
            rec['status'] = 'running'
        elif e == 'stage_done':
            rec['status'] = 'ok'
            rec['elapsed_s'] = ev.get('elapsed', 0.0) or 0.0
            rec['detail'] = ev.get('detail', '') or ''
        elif e == 'stage_fail':
            rec['status'] = 'failed'
            rec['elapsed_s'] = ev.get('elapsed', 0.0) or 0.0
            rec['detail'] = ev.get('error', '') or ''
        elif e == 'stage_warn':
            rec['status'] = 'warning'
            rec['elapsed_s'] = ev.get('elapsed', 0.0) or 0.0
            rec['detail'] = ev.get('detail', '') or ''
    _fold_node_events(by_stage, events, subject_filter=subject_filter)
    return list(by_stage.values())


def _events_to_group_stages(events: list[dict]) -> list[dict]:
    """Same as the subject helper but consumes ``group_stage_*`` events.

    Node-level events (group_analyzers / group_reporters running inside
    ``_record``) get folded into the matching ``group_analyze`` /
    ``group_report`` stage so the live graph shows which group plugin
    is currently active.
    """
    by_stage: dict[str, dict] = {}
    for ev in events:
        e = ev.get('event')
        stage = ev.get('stage')
        if not stage:
            continue
        if e not in ('group_stage_start', 'group_stage_done', 'group_stage_fail'):
            continue
        rec = by_stage.setdefault(stage, {
            'name': stage, 'status': 'running',
            'elapsed_s': 0.0, 'detail': '', 'nodes': [],
        })
        if e == 'group_stage_start':
            rec['status'] = 'running'
        elif e == 'group_stage_done':
            rec['status'] = 'ok'
            rec['elapsed_s'] = ev.get('elapsed', 0.0) or 0.0
        elif e == 'group_stage_fail':
            rec['status'] = 'failed'
            rec['elapsed_s'] = ev.get('elapsed', 0.0) or 0.0
            rec['detail'] = ev.get('error', '') or ''
    # The orchestrator emits node_* events for group_analyzers /
    # group_reporters with node_id prefixed by the group stage name
    # ("group_analyze:foo"). _fold_node_events keys by that prefix so
    # they land on the right StageRecord.
    _fold_node_events(by_stage, [
        ev for ev in events
        # Only fold node events not tagged with a subject (those
        # belong to subject pipelines inside the fanout, handled by
        # _events_to_subject_summaries).
        if not ev.get('subject')
    ])
    return list(by_stage.values())


def _events_to_study_stages(events: list[dict]) -> list[dict]:
    by_stage: dict[str, dict] = {}
    for ev in events:
        e = ev.get('event')
        stage = ev.get('stage')
        if not stage:
            continue
        if e not in ('study_stage_start', 'study_stage_done', 'study_stage_fail'):
            continue
        rec = by_stage.setdefault(stage, {
            'name': stage, 'status': 'running',
            'elapsed_s': 0.0, 'detail': '', 'nodes': [],
        })
        if e == 'study_stage_start':
            rec['status'] = 'running'
        elif e == 'study_stage_done':
            rec['status'] = 'ok'
            rec['elapsed_s'] = ev.get('elapsed', 0.0) or 0.0
        elif e == 'study_stage_fail':
            rec['status'] = 'failed'
            rec['elapsed_s'] = ev.get('elapsed', 0.0) or 0.0
            rec['detail'] = ev.get('error', '') or ''
    # Same shape as the group case — fold study_analyze / study_report
    # node events. node_id is prefixed with the study stage name so the
    # generic helper places them correctly.
    _fold_node_events(by_stage, [
        ev for ev in events
        if not ev.get('subject') and not ev.get('group_label')
    ])
    return list(by_stage.values())


def _events_to_subject_summaries(events: list[dict],
                                 group_label: str | None = None) -> list[dict]:
    """Build partial RunSummary dicts, one per subject seen in events.

    Picks up ``group_subject_start/done`` for the subject list and the
    subject-tagged ``stage_*`` events (the ones the GroupOrchestrator
    re-emits inside ``ui.event_context(subject=...)``) for each
    subject's stage table. When ``group_label`` is given, only events
    matching that label are considered (study-scope filter).
    """
    subject_stages: dict[str, dict[str, dict]] = {}
    subject_meta: dict[str, dict] = {}

    def matches_group(ev: dict) -> bool:
        if group_label is None:
            return True
        return (
            ev.get('group_label') == group_label
            or ev.get('group') == group_label
        )

    for ev in events:
        if not matches_group(ev):
            continue
        e = ev.get('event')
        sub = ev.get('subject')
        if e == 'group_subject_start' and sub:
            subject_meta.setdefault(sub, {'subject': sub})
        elif e == 'group_subject_done' and sub:
            subject_meta.setdefault(sub, {'subject': sub})
            subject_meta[sub]['total_elapsed_s'] = ev.get('elapsed', 0.0) or 0.0
        elif e in ('stage_start', 'stage_done', 'stage_fail', 'stage_warn'):
            if not sub:
                continue
            stage = ev.get('stage')
            if not stage:
                continue
            stages = subject_stages.setdefault(sub, {})
            rec = stages.setdefault(stage, {
                'name': stage, 'status': 'running',
                'elapsed_s': 0.0, 'detail': '',
            })
            if e == 'stage_start':
                rec['status'] = 'running'
            elif e == 'stage_done':
                rec['status'] = 'ok'
                rec['elapsed_s'] = ev.get('elapsed', 0.0) or 0.0
                rec['detail'] = ev.get('detail', '') or ''
            elif e == 'stage_fail':
                rec['status'] = 'failed'
                rec['elapsed_s'] = ev.get('elapsed', 0.0) or 0.0
                rec['detail'] = ev.get('error', '') or ''
            elif e == 'stage_warn':
                rec['status'] = 'warning'
                rec['elapsed_s'] = ev.get('elapsed', 0.0) or 0.0
                rec['detail'] = ev.get('detail', '') or ''

    # Merge meta + stages into RunSummary-shaped dicts. Also fold any
    # subject-tagged node_* events into the right StageRecord so the
    # subject's drill-down graph shows per-plugin live status.
    out: list[dict] = []
    subjects = set(subject_meta.keys()) | set(subject_stages.keys())
    for sub in sorted(subjects):
        meta = subject_meta.get(sub, {'subject': sub})
        stages_dict = dict(subject_stages.get(sub, {}))
        # Only consider node events tagged with this subject + label.
        sub_node_events = [
            ev for ev in events
            if ev.get('subject') == sub and matches_group(ev)
        ]
        _fold_node_events(stages_dict, sub_node_events)
        out.append({
            'subject': sub,
            'experiment': '',
            'started_at': '', 'finished_at': '',
            'total_elapsed_s': meta.get('total_elapsed_s', 0.0),
            'stages': list(stages_dict.values()),
            'config_snapshot': {},
        })
    return out


def _events_to_group_summaries(events: list[dict],
                               group_labels: list[str]) -> list[dict]:
    """Per-group partial GroupRunSummary dicts for a study run."""
    out: list[dict] = []
    for label in group_labels:
        out.append({
            'group_name': label,
            'subjects': [],
            'started_at': '', 'finished_at': '', 'total_elapsed_s': 0.0,
            'subject_summaries': _events_to_subject_summaries(events, label),
            'group_stages': [
                rec for rec in (
                    _events_to_group_stages([
                        ev for ev in events
                        if ev.get('group') == label
                           or ev.get('group_label') == label
                    ])
                )
            ],
            'config_snapshot': {},
            'run_id': '',
        })
    return out


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


# ── config preview (no run yet) ────────────────────────────────────────


@router.get("/configs/{filename}/graph")
async def config_graph(request: Request, filename: str):
    """Build the graph for a config that hasn't been run.

    Stage status is ``unknown`` for every node since no run has
    happened — the value here is seeing the plugin structure and
    jumping into source code from the Dashboard before launching a
    run. Works for both subject and group configs.
    """
    store = request.app.state.config_store
    result = store.get_config(filename)
    if result is None:
        raise HTTPException(status_code=404,
                            detail=f"Config '{filename}' not found")
    cfg = result.get('config') or {}
    registry = _registry(request)

    is_group = (
        isinstance(cfg.get('group'), str)
        and isinstance(cfg.get('subjects'), list)
    )

    if is_group:
        # Synthesize a minimal GroupRunSummary-shaped dict so the
        # group-graph builder can render its skeleton.
        graph = build_group_graph({
            'group_name': cfg.get('group'),
            'config_snapshot': cfg,
            'group_stages': [],
            'subject_summaries': [
                {'subject': s, 'stages': [], 'config_snapshot': {}}
                for s in cfg.get('subjects') or []
            ],
        }, registry)
        return {
            'filename': filename,
            'kind': 'group',
            'group_name': cfg.get('group'),
            **graph.to_dict(),
        }
    # Subject config: use the per-subject template directly. There are
    # no recorded stages yet so every plugin gets status='unknown'.
    graph = build_subject_graph(cfg, [], registry)
    return {
        'filename': filename,
        'kind': 'subject',
        'experiment': cfg.get('experiment', ''),
        'subject': cfg.get('subject', ''),
        **graph.to_dict(),
    }


@router.get("/configs/{filename}/node/{node_id:path}/source")
async def config_node_source(request: Request, filename: str, node_id: str):
    """Source code for one node in a config-preview graph."""
    store = request.app.state.config_store
    result = store.get_config(filename)
    if result is None:
        raise HTTPException(status_code=404,
                            detail=f"Config '{filename}' not found")
    cfg = result.get('config') or {}
    registry = _registry(request)
    is_group = (
        isinstance(cfg.get('group'), str)
        and isinstance(cfg.get('subjects'), list)
    )
    if is_group:
        graph = build_group_graph({
            'group_name': cfg.get('group'),
            'config_snapshot': cfg,
            'group_stages': [],
            'subject_summaries': [],
        }, registry).to_dict()
    else:
        graph = build_subject_graph(cfg, [], registry).to_dict()
    node = _find_node(graph, node_id)
    if not node.get('source_path'):
        raise HTTPException(
            status_code=404,
            detail=f"No source registered for node '{node_id}'",
        )
    return _serve_source(node['source_path'])


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


# ── study run ───────────────────────────────────────────────────────────


@router.get("/study-runs/{name}/{run_id}/graph")
async def study_run_graph(request: Request, name: str, run_id: str):
    run_dir = _resolve_study_run_dir(name, run_id)
    summary = _read_study_summary(run_dir)
    graph = build_study_graph(summary, _registry(request))
    return {
        'study_name': summary.get('study_name', name),
        'run_id': run_id,
        'output_dir': str(run_dir),
        **graph.to_dict(),
    }


@router.get("/study-runs/{name}/{run_id}/node/{node_id:path}/source")
async def study_node_source(request: Request, name: str, run_id: str,
                            node_id: str):
    run_dir = _resolve_study_run_dir(name, run_id)
    summary = _read_study_summary(run_dir)
    graph = build_study_graph(summary, _registry(request)).to_dict()
    node = _find_node(graph, node_id)
    if not node.get('source_path'):
        raise HTTPException(
            status_code=404,
            detail=f"No source registered for node '{node_id}'",
        )
    return _serve_source(node['source_path'])


@router.get("/study-runs/{name}/{run_id}/node/{node_id:path}/outputs")
async def study_node_outputs(request: Request, name: str, run_id: str,
                             node_id: str):
    run_dir = _resolve_study_run_dir(name, run_id)
    summary = _read_study_summary(run_dir)
    graph = build_study_graph(summary, _registry(request)).to_dict()
    node = _find_node(graph, node_id)
    files = list_node_outputs(run_dir, GraphNode(**{
        k: v for k, v in node.items() if k in GraphNode.__dataclass_fields__
    }))
    return {
        'node_id': node_id,
        'output_dir': str(run_dir),
        'files': files,
    }


@router.get("/study-runs/{name}/{run_id}/node/{node_id:path}/file/{rel:path}")
async def study_node_file(name: str, run_id: str, node_id: str, rel: str):
    run_dir = _resolve_study_run_dir(name, run_id)
    full = _safe_join(run_dir, rel)
    return FileResponse(str(full))


@router.get("/study-runs/{name}/{run_id}/group/{label}/graph")
async def study_group_graph(request: Request, name: str, run_id: str,
                            label: str):
    """Drill into a group inside a study — yields a regular group graph."""
    study_run_dir = _resolve_study_run_dir(name, run_id)
    group_run_dir = _resolve_study_group_run_dir(study_run_dir, label)
    group_summary = json.loads((group_run_dir / 'group_summary.json').read_text())
    graph = build_group_graph(group_summary, _registry(request))
    return {
        'study_name': name,
        'run_id': run_id,
        'group_label': label,
        'group_name': group_summary.get('group_name', label),
        'output_dir': str(group_run_dir),
        **graph.to_dict(),
    }


@router.get("/study-runs/{name}/{run_id}/group/{label}/node/{node_id:path}/source")
async def study_group_node_source(request: Request, name: str, run_id: str,
                                  label: str, node_id: str):
    study_run_dir = _resolve_study_run_dir(name, run_id)
    group_run_dir = _resolve_study_group_run_dir(study_run_dir, label)
    group_summary = json.loads((group_run_dir / 'group_summary.json').read_text())
    graph = build_group_graph(group_summary, _registry(request)).to_dict()
    node = _find_node(graph, node_id)
    if not node.get('source_path'):
        raise HTTPException(
            status_code=404,
            detail=f"No source registered for node '{node_id}'",
        )
    return _serve_source(node['source_path'])


@router.get("/study-runs/{name}/{run_id}/group/{label}/node/{node_id:path}/outputs")
async def study_group_node_outputs(request: Request, name: str, run_id: str,
                                   label: str, node_id: str):
    study_run_dir = _resolve_study_run_dir(name, run_id)
    group_run_dir = _resolve_study_group_run_dir(study_run_dir, label)
    group_summary = json.loads((group_run_dir / 'group_summary.json').read_text())
    graph = build_group_graph(group_summary, _registry(request)).to_dict()
    node = _find_node(graph, node_id)
    files = list_node_outputs(group_run_dir, GraphNode(**{
        k: v for k, v in node.items() if k in GraphNode.__dataclass_fields__
    }))
    return {
        'node_id': node_id,
        'output_dir': str(group_run_dir),
        'files': files,
    }


@router.get("/study-runs/{name}/{run_id}/group/{label}/node/{node_id:path}/file/{rel:path}")
async def study_group_node_file(name: str, run_id: str, label: str,
                                node_id: str, rel: str):
    study_run_dir = _resolve_study_run_dir(name, run_id)
    group_run_dir = _resolve_study_group_run_dir(study_run_dir, label)
    full = _safe_join(group_run_dir, rel)
    return FileResponse(str(full))


# ── in-flight live graph ───────────────────────────────────────────────


def _in_flight_handle(request: Request, run_id: str):
    """Return the active RunHandle for ``run_id``, or 404."""
    manager = request.app.state.run_manager
    handle = manager.active_runs.get(run_id)
    if handle is None:
        raise HTTPException(status_code=404,
                            detail=f"in-flight run '{run_id}' not found")
    return handle


def _resolve_in_flight_output_dir(handle) -> Path | None:
    """Find the on-disk directory where this in-flight run is writing.

    For subject runs, ``handle.output_dir`` is the actual run dir.
    For group / study runs, ``handle.output_dir`` is the parent and
    the active run lives in ``<parent>/<latest>/``; we resolve the
    ``latest`` symlink (or the newest subdir) so this endpoint works
    even before the summary file is written.
    """
    if not handle.output_dir:
        return None
    base = Path(handle.output_dir)
    if not (handle.is_group or handle.is_study):
        return base
    if not base.is_dir():
        return None
    latest = base / 'latest'
    if latest.is_symlink() or latest.exists():
        try:
            resolved = latest.resolve()
            if resolved.is_dir():
                return resolved
        except OSError:
            pass
    candidates = [
        p for p in base.iterdir()
        if p.is_dir() and p.name != 'latest'
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def _in_flight_graph_dict(request: Request, handle) -> dict:
    """Build the graph dict the same way the GET endpoint returns it."""
    registry = _registry(request)
    events = list(handle.events or [])
    cfg = handle.config or {}
    if handle.is_study:
        labels = [str(e.get('name')) for e in cfg.get('groups', [])
                  if isinstance(e, dict) and e.get('name')]
        summary = {
            'config_snapshot': cfg,
            'study_stages': _events_to_study_stages(events),
            'group_summaries': _events_to_group_summaries(events, labels),
            'group_labels': labels,
        }
        return build_study_graph(summary, registry).to_dict()
    if handle.is_group:
        summary = {
            'config_snapshot': cfg,
            'group_stages': _events_to_group_stages(events),
            'subject_summaries': _events_to_subject_summaries(events),
            'subjects': cfg.get('subjects') or [],
        }
        return build_group_graph(summary, registry).to_dict()
    return build_subject_graph(
        cfg, _events_to_subject_stages(events), registry,
    ).to_dict()


@router.get("/runs/in-flight/{run_id}/node/{node_id:path}/source")
async def in_flight_node_source(request: Request, run_id: str, node_id: str):
    handle = _in_flight_handle(request, run_id)
    graph = _in_flight_graph_dict(request, handle)
    node = _find_node(graph, node_id)
    if not node.get('source_path'):
        raise HTTPException(
            status_code=404,
            detail=f"No source registered for node '{node_id}'",
        )
    return _serve_source(node['source_path'])


@router.get("/runs/in-flight/{run_id}/node/{node_id:path}/outputs")
async def in_flight_node_outputs(request: Request, run_id: str, node_id: str):
    handle = _in_flight_handle(request, run_id)
    graph = _in_flight_graph_dict(request, handle)
    node = _find_node(graph, node_id)
    output_dir = _resolve_in_flight_output_dir(handle)
    files: list[dict] = []
    if output_dir is not None and output_dir.is_dir():
        files = list_node_outputs(output_dir, GraphNode(**{
            k: v for k, v in node.items() if k in GraphNode.__dataclass_fields__
        }))
    return {
        'node_id': node_id,
        'output_dir': str(output_dir) if output_dir else '',
        'files': files,
    }


@router.get("/runs/in-flight/{run_id}/node/{node_id:path}/file/{rel:path}")
async def in_flight_node_file(request: Request, run_id: str,
                              node_id: str, rel: str):
    handle = _in_flight_handle(request, run_id)
    output_dir = _resolve_in_flight_output_dir(handle)
    if output_dir is None:
        raise HTTPException(status_code=404, detail="output dir not yet on disk")
    full = _safe_join(output_dir, rel)
    return FileResponse(str(full))


# ── live log tails ──


def _read_log_tail_safe(path: Path | str | None, n: int = 500) -> tuple[str, str]:
    """Return (tail, path_str). Empty tail if the file doesn't exist
    yet — common for log files that the subprocess hasn't started
    writing to."""
    if not path:
        return ('', '')
    p = Path(path) if not isinstance(path, Path) else path
    if not p.is_file():
        return ('', str(p))
    try:
        text = p.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return ('', str(p))
    lines = text.splitlines()
    return ('\n'.join(lines[-n:]), str(p))


@router.get("/runs/in-flight/{run_id}/log")
async def in_flight_log(request: Request, run_id: str, tail: int = 500):
    """Tail the run-scope log for a live run.

    For subject runs this is the subprocess stdout. For group / study
    runs we prefer the orchestrator's own ``group.log`` / ``study.log``
    inside the run dir (richer than the subprocess stdout), falling
    back to the subprocess log if those don't exist yet.
    """
    handle = _in_flight_handle(request, run_id)
    candidates: list[Path | str | None] = []
    if handle.is_study:
        run_dir = _resolve_in_flight_output_dir(handle)
        if run_dir is not None:
            candidates.append(run_dir / 'study.log')
    elif handle.is_group:
        run_dir = _resolve_in_flight_output_dir(handle)
        if run_dir is not None:
            candidates.append(run_dir / 'group.log')
    candidates.append(handle.log_path)

    for c in candidates:
        text, path = _read_log_tail_safe(c, n=tail)
        if text:
            return {'log_tail': text, 'log_path': path}
    return {'log_tail': '', 'log_path': str(handle.log_path or '')}


@router.get("/runs/in-flight/{run_id}/subject/{sub}/log")
async def in_flight_subject_log(request: Request, run_id: str,
                                sub: str, tail: int = 500):
    """Tail one subject's pipeline.log inside an active group/study run."""
    handle = _in_flight_handle(request, run_id)
    sub_dir = _resolve_in_flight_subject_dir(handle, sub)
    log_path = (sub_dir / 'pipeline.log') if sub_dir is not None else None
    text, path = _read_log_tail_safe(log_path, n=tail)
    return {'log_tail': text, 'log_path': path}


# ── in-flight subject drilldown (clickable subject nodes in a live group) ──


def _live_subject_config(group_cfg: dict, subject: str) -> dict:
    """Resolve the subject-scope config for one subject of a live
    group / study run, well enough to draw a graph.

    The group YAML's ``subject_template`` is the base; per-subject
    ``subject_overrides[subject]`` deep-merges on top — matching what
    :class:`GroupOrchestrator` does at run time so the graph reflects
    the actual subject config the pipeline is using.
    """
    from fmriflow.config.loader import merge_configs
    import copy as _copy
    base = _copy.deepcopy(group_cfg.get('subject_template') or {})
    overrides = (group_cfg.get('subject_overrides') or {}).get(subject) or {}
    merged = merge_configs(base, overrides)
    merged['subject'] = subject
    if not merged.get('experiment'):
        merged['experiment'] = group_cfg.get('group') or ''
    return merged


def _resolve_in_flight_subject_dir(handle, subject: str) -> Path | None:
    """The per-subject output dir inside an active group / study run."""
    run_dir = _resolve_in_flight_output_dir(handle)
    if run_dir is None:
        return None
    sub_dir = run_dir / 'subjects' / subject
    if not sub_dir.is_dir():
        return None
    return sub_dir


@router.get("/runs/in-flight/{run_id}/subject/{sub}/graph")
async def in_flight_subject_graph(request: Request, run_id: str, sub: str):
    handle = _in_flight_handle(request, run_id)
    if not (handle.is_group or handle.is_study):
        raise HTTPException(
            status_code=400,
            detail="subject drilldown only valid on group / study runs",
        )
    cfg = handle.config or {}
    events = list(handle.events or [])
    subject_cfg = _live_subject_config(cfg, sub)
    stages = _events_to_subject_stages(events, subject_filter=sub)
    graph = build_subject_graph(subject_cfg, stages, _registry(request))
    return {
        'run_id': run_id,
        'subject': sub,
        'experiment': subject_cfg.get('experiment', ''),
        'live': True,
        **graph.to_dict(),
    }


@router.get("/runs/in-flight/{run_id}/subject/{sub}/node/{node_id:path}/source")
async def in_flight_subject_node_source(request: Request, run_id: str,
                                        sub: str, node_id: str):
    handle = _in_flight_handle(request, run_id)
    cfg = handle.config or {}
    subject_cfg = _live_subject_config(cfg, sub)
    events = list(handle.events or [])
    stages = _events_to_subject_stages(events, subject_filter=sub)
    graph = build_subject_graph(
        subject_cfg, stages, _registry(request),
    ).to_dict()
    node = _find_node(graph, node_id)
    if not node.get('source_path'):
        raise HTTPException(
            status_code=404,
            detail=f"No source registered for node '{node_id}'",
        )
    return _serve_source(node['source_path'])


@router.get("/runs/in-flight/{run_id}/subject/{sub}/node/{node_id:path}/outputs")
async def in_flight_subject_node_outputs(request: Request, run_id: str,
                                         sub: str, node_id: str):
    handle = _in_flight_handle(request, run_id)
    cfg = handle.config or {}
    subject_cfg = _live_subject_config(cfg, sub)
    events = list(handle.events or [])
    stages = _events_to_subject_stages(events, subject_filter=sub)
    graph = build_subject_graph(
        subject_cfg, stages, _registry(request),
    ).to_dict()
    node = _find_node(graph, node_id)
    sub_dir = _resolve_in_flight_subject_dir(handle, sub)
    files: list[dict] = []
    if sub_dir is not None:
        files = list_node_outputs(sub_dir, GraphNode(**{
            k: v for k, v in node.items() if k in GraphNode.__dataclass_fields__
        }))
    return {
        'node_id': node_id,
        'output_dir': str(sub_dir) if sub_dir else '',
        'files': files,
    }


@router.get("/runs/in-flight/{run_id}/subject/{sub}/node/{node_id:path}/file/{rel:path}")
async def in_flight_subject_node_file(request: Request, run_id: str,
                                      sub: str, node_id: str, rel: str):
    handle = _in_flight_handle(request, run_id)
    sub_dir = _resolve_in_flight_subject_dir(handle, sub)
    if sub_dir is None:
        raise HTTPException(
            status_code=404,
            detail=f"subject dir not yet on disk for '{sub}'",
        )
    full = _safe_join(sub_dir, rel)
    return FileResponse(str(full))


@router.get("/runs/in-flight/{run_id}/graph")
async def in_flight_graph(request: Request, run_id: str):
    """Live pipeline graph for a run still in progress.

    Looks up the run in :class:`RunManager.active_runs`, synthesizes
    StageRecord-shaped dicts from ``handle.events`` (no run_summary
    yet — the subprocess is still running), and feeds them through
    the matching ``build_*_graph`` builder. Returns the same
    ``{nodes, edges, …}`` shape as the finished-run endpoints so the
    frontend modal can render it identically.

    Poll this endpoint client-side to see status flip from
    ``running`` to ``ok`` / ``failed`` as each stage completes.
    """
    manager = request.app.state.run_manager
    handle = manager.active_runs.get(run_id)
    if handle is None:
        raise HTTPException(status_code=404,
                            detail=f"in-flight run '{run_id}' not found")
    registry = _registry(request)
    events = list(handle.events or [])
    cfg = handle.config or {}

    if handle.is_study:
        labels = [str(e.get('name')) for e in cfg.get('groups', [])
                  if isinstance(e, dict) and e.get('name')]
        summary = {
            'study_name': cfg.get('study') or '',
            'run_id': run_id,
            'group_labels': labels,
            'started_at': '', 'finished_at': '', 'total_elapsed_s': 0.0,
            'study_stages': _events_to_study_stages(events),
            'group_summaries': _events_to_group_summaries(events, labels),
            'config_snapshot': cfg,
        }
        graph = build_study_graph(summary, registry)
        return {
            'study_name': summary['study_name'],
            'run_id': run_id,
            'live': True,
            **graph.to_dict(),
        }

    if handle.is_group:
        summary = {
            'group_name': cfg.get('group') or '',
            'run_id': run_id,
            'subjects': cfg.get('subjects') or [],
            'started_at': '', 'finished_at': '', 'total_elapsed_s': 0.0,
            'group_stages': _events_to_group_stages(events),
            'subject_summaries': _events_to_subject_summaries(events),
            'config_snapshot': cfg,
        }
        graph = build_group_graph(summary, registry)
        return {
            'group_name': summary['group_name'],
            'run_id': run_id,
            'live': True,
            **graph.to_dict(),
        }

    # Subject run.
    stages = _events_to_subject_stages(events)
    graph = build_subject_graph(cfg, stages, registry)
    return {
        'run_id': run_id,
        'experiment': cfg.get('experiment', ''),
        'subject': cfg.get('subject', ''),
        'live': True,
        **graph.to_dict(),
    }
