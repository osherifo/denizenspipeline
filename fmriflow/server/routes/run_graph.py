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
    build_graph_run_graph,
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


def _resolve_group_run_dir(
    request: Request, group_name: str, run_id: str,
) -> Path:
    """Return the on-disk dir for a group run, or raise 404.

    Delegates to the registry-backed resolver in ``run_manager`` so
    runs whose ``output_dir`` is anywhere on disk (i.e. outside
    ``$FMRIFLOW_HOME``) are still discoverable. The previous local
    implementation hardcoded ``paths.group_runs_root() / name / run_id``
    and failed for those.
    """
    if not group_name or '/' in group_name or group_name.startswith('.'):
        raise HTTPException(status_code=400, detail="invalid group name")
    if not run_id or '/' in run_id or run_id.startswith('.'):
        raise HTTPException(status_code=400, detail="invalid run_id")
    from fmriflow.server.services.run_manager import resolve_group_run_dir
    registry = request.app.state.run_manager.registry
    root = request.query_params.get('root')
    run_dir = resolve_group_run_dir(registry, group_name, run_id, root_id=root)
    if run_dir is None:
        raise HTTPException(
            status_code=404,
            detail=f"group run not found: {group_name}/{run_id}")
    return run_dir


def _read_group_summary(run_dir: Path) -> dict:
    return json.loads((run_dir / 'group_summary.json').read_text())


def _resolve_study_run_dir(
    request: Request, study_name: str, run_id: str,
) -> Path:
    """Study analogue of :func:`_resolve_group_run_dir`."""
    if not study_name or '/' in study_name or study_name.startswith('.'):
        raise HTTPException(status_code=400, detail="invalid study name")
    if not run_id or '/' in run_id or run_id.startswith('.'):
        raise HTTPException(status_code=400, detail="invalid run_id")
    from fmriflow.server.services.run_manager import resolve_study_run_dir
    registry = request.app.state.run_manager.registry
    root = request.query_params.get('root')
    run_dir = resolve_study_run_dir(registry, study_name, run_id, root_id=root)
    if run_dir is None:
        raise HTTPException(
            status_code=404,
            detail=f"study run not found: {study_name}/{run_id}")
    return run_dir


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


def _subject_run_graph(request: Request, run: dict) -> dict:
    """Run graph dict for a subject run: from the executed ``graph.json`` when
    the run has one (graph engine), else re-derived from the config snapshot."""
    summary = run['summary']
    records = [s.__dict__ if hasattr(s, '__dict__') else s for s in summary.stages]
    graph_json = Path(run['output_dir']) / 'graph.json'
    if graph_json.is_file():
        try:
            doc = json.loads(graph_json.read_text())
            out = build_graph_run_graph(doc, records, _registry(request)).to_dict()
            out['graph_doc'] = doc
            return out
        except Exception:
            logger.warning("Could not build the run graph from %s; using the config snapshot",
                           graph_json, exc_info=True)
    return build_subject_graph(summary.config_snapshot, records, _registry(request)).to_dict()


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
                                 group_label: str | None = None,
                                 *, group_names: list[str] | None = None) -> list[dict]:
    """Build partial RunSummary dicts, one per subject seen in events.

    Picks up ``group_subject_start/done`` for the subject list and the
    subject-tagged ``stage_*`` events (the ones the GroupOrchestrator
    re-emits inside ``ui.event_context(subject=...)``) for each
    subject's stage table.

    Filtering: when ``group_label`` is given, events whose
    ``group_label`` matches it count. Inside a study run the
    GroupOrchestrator runs its subjects in a ``ThreadPoolExecutor`` —
    the worker threads don't inherit the parent thread's
    ``event_context``, so subject-emitted events carry only the
    *internal* group name (e.g. ``modality_a_group``), not the
    study-scope label (e.g. ``reading``). ``group_names`` lets callers
    pass those internal names so subject events still match.
    """
    subject_stages: dict[str, dict[str, dict]] = {}
    subject_meta: dict[str, dict] = {}

    accept: set[str] = set()
    if group_label:
        accept.add(group_label)
    if group_names:
        accept.update(n for n in group_names if n)

    def matches_group(ev: dict) -> bool:
        if not accept:
            return True
        return (
            ev.get('group_label') in accept
            or ev.get('group') in accept
        )

    for ev in events:
        if not matches_group(ev):
            continue
        e = ev.get('event')
        sub = ev.get('subject')
        if e == 'group_subject_start' and sub:
            meta = subject_meta.setdefault(sub, {'subject': sub})
            # First start wins — a started-but-not-yet-done subject
            # should colour 'running' even before its first stage
            # emits a stage_start.
            meta.setdefault('status', 'running')
        elif e == 'group_subject_done' and sub:
            meta = subject_meta.setdefault(sub, {'subject': sub})
            meta['total_elapsed_s'] = ev.get('elapsed', 0.0) or 0.0
            reported = ev.get('status')
            meta['status'] = (
                reported if reported in ('ok', 'failed', 'warning')
                else 'ok'
            )
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
        entry = {
            'subject': sub,
            'experiment': '',
            'started_at': '', 'finished_at': '',
            'total_elapsed_s': meta.get('total_elapsed_s', 0.0),
            'stages': list(stages_dict.values()),
            'config_snapshot': {},
        }
        # Forward the live status only when the per-stage rollup
        # wouldn't already say so — otherwise we'd shadow a 'failed'
        # stage with a stale 'running' meta entry.
        live = meta.get('status')
        if live is not None:
            entry['status'] = live
        out.append(entry)
    return out


def _events_to_group_summaries(events: list[dict],
                               group_labels: list[str],
                               *, label_to_group_name: dict[str, str] | None = None,
                               ) -> list[dict]:
    """Per-group partial GroupRunSummary dicts for a study run.

    Also stamps a coarse live ``status`` per group derived from
    ``study_group_start`` / ``study_group_done`` / ``study_group_fail``
    events so the in-flight study graph can colour each group node
    correctly *before* any subject has finished its first stage
    (otherwise the group node sits at 'unknown' / grey while the
    group is actively running).

    ``label_to_group_name`` maps each study-scope label
    (e.g. ``reading``) to the underlying group's internal name
    (e.g. ``modality_a_group``) so subject-emitted events — which
    the GroupOrchestrator's worker threads emit with only the
    internal name (the study's ``event_context`` doesn't cross the
    thread boundary) — still get attributed to the right group.
    """
    # First pass: collect per-label start/done state from the study
    # orchestrator's wrapper events.
    live_status: dict[str, str] = {}
    for ev in events:
        name = ev.get('event')
        label = ev.get('group_label') or ev.get('group')
        if not label:
            continue
        if name == 'study_group_start':
            live_status.setdefault(label, 'running')
        elif name == 'study_group_done':
            reported = ev.get('status')
            live_status[label] = (
                reported if reported in ('ok', 'failed', 'warning')
                else 'ok'
            )
        elif name == 'study_group_fail':
            live_status[label] = 'failed'

    mapping = label_to_group_name or {}
    out: list[dict] = []
    for label in group_labels:
        accept = {label}
        if mapping.get(label):
            accept.add(mapping[label])
        out.append({
            'group_name': mapping.get(label, label),
            'subjects': [],
            'started_at': '', 'finished_at': '', 'total_elapsed_s': 0.0,
            'subject_summaries': _events_to_subject_summaries(
                events, label,
                group_names=[mapping[label]] if mapping.get(label) else None,
            ),
            'group_stages': [
                rec for rec in (
                    _events_to_group_stages([
                        ev for ev in events
                        if ev.get('group') in accept
                           or ev.get('group_label') in accept
                    ])
                )
            ],
            'config_snapshot': {},
            'run_id': '',
            # No start event yet — this group hasn't been reached.
            'status': live_status.get(label, 'pending'),
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

    Stage status is ``pending`` for every node since no run has
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
    # no recorded stages yet so every plugin gets status='pending'.
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


def _resolve_config_subject(request: Request, filename: str,
                            sub: str) -> dict:
    """Build the resolved per-subject config for a group config preview.

    Returns the dict that the group orchestrator *would* feed to a
    subject pipeline for ``sub``. Raises HTTPException(404) if the
    config isn't a group config or doesn't list this subject.
    """
    # Local import to avoid circular import at module load.
    from fmriflow.group_orchestrator import derive_subject_config
    from fmriflow.exceptions import ConfigError

    store = request.app.state.config_store
    result = store.get_config(filename)
    if result is None:
        raise HTTPException(status_code=404,
                            detail=f"Config '{filename}' not found")
    cfg = result.get('config') or {}
    if not (isinstance(cfg.get('group'), str)
            and isinstance(cfg.get('subjects'), list)):
        raise HTTPException(
            status_code=404,
            detail=f"Config '{filename}' is not a group config",
        )
    if sub not in cfg['subjects']:
        raise HTTPException(
            status_code=404,
            detail=f"Subject '{sub}' not declared in group config '{filename}'",
        )
    try:
        return derive_subject_config(cfg, sub, validate=False)
    except ConfigError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/configs/{filename}/subject/{sub}/graph")
async def config_subject_graph(request: Request, filename: str, sub: str):
    """Preview the 7-stage subject graph for one subject of a group config.

    No run has happened — every stage/plugin gets status='pending'. The
    per-subject config is derived from the group YAML using the same
    template/override/defaults logic the orchestrator uses at run time.
    """
    sub_cfg = _resolve_config_subject(request, filename, sub)
    graph = build_subject_graph(sub_cfg, [], _registry(request))
    return {
        'filename': filename,
        'kind': 'config-subject',
        'subject': sub,
        'experiment': sub_cfg.get('experiment', ''),
        **graph.to_dict(),
    }


@router.get("/configs/{filename}/subject/{sub}/node/{node_id:path}/source")
async def config_subject_node_source(request: Request, filename: str,
                                     sub: str, node_id: str):
    """Source code for one node in a config-subject preview graph."""
    sub_cfg = _resolve_config_subject(request, filename, sub)
    graph = build_subject_graph(
        sub_cfg, [], _registry(request),
    ).to_dict()
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
    return {
        'run_id': run_id,
        'experiment': summary.experiment,
        'subject': summary.subject,
        'output_dir': run['output_dir'],
        **_subject_run_graph(request, run),
    }


@router.get("/runs/{run_id}/node/{node_id:path}/source")
async def subject_node_source(request: Request, run_id: str, node_id: str):
    run = _find_run_or_404(request, run_id)
    graph = _subject_run_graph(request, run)
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
    graph = _subject_run_graph(request, run)
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
    run_dir = _resolve_group_run_dir(request, name, run_id)
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
    run_dir = _resolve_group_run_dir(request, name, run_id)
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
    run_dir = _resolve_group_run_dir(request, name, run_id)
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
async def group_node_file(request: Request, name: str, run_id: str, node_id: str, rel: str):
    run_dir = _resolve_group_run_dir(request, name, run_id)
    full = _safe_join(run_dir, rel)
    return FileResponse(str(full))


@router.get("/group-runs/{name}/{run_id}/subject/{sub}/graph")
async def group_subject_graph(request: Request, name: str, run_id: str,
                              sub: str):
    """Zoom-in: the 7-stage subject graph for one subject of a group run."""
    run_dir = _resolve_group_run_dir(request, name, run_id)
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
    run_dir = _resolve_group_run_dir(request, name, run_id)
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
    run_dir = _resolve_group_run_dir(request, name, run_id)
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
async def group_subject_node_file(request: Request, name: str, run_id: str, sub: str,
                                  node_id: str, rel: str):
    run_dir = _resolve_group_run_dir(request, name, run_id)
    sub_dir = run_dir / 'subjects' / sub
    if not sub_dir.is_dir():
        raise HTTPException(status_code=404,
                            detail=f"subject dir not found: {sub}")
    full = _safe_join(sub_dir, rel)
    return FileResponse(str(full))


# ── study run ───────────────────────────────────────────────────────────


@router.get("/study-runs/{name}/{run_id}/graph")
async def study_run_graph(request: Request, name: str, run_id: str):
    run_dir = _resolve_study_run_dir(request, name, run_id)
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
    run_dir = _resolve_study_run_dir(request, name, run_id)
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
    run_dir = _resolve_study_run_dir(request, name, run_id)
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
async def study_node_file(request: Request, name: str, run_id: str, node_id: str, rel: str):
    run_dir = _resolve_study_run_dir(request, name, run_id)
    full = _safe_join(run_dir, rel)
    return FileResponse(str(full))


@router.get("/study-runs/{name}/{run_id}/group/{label}/graph")
async def study_group_graph(request: Request, name: str, run_id: str,
                            label: str):
    """Drill into a group inside a study — yields a regular group graph."""
    study_run_dir = _resolve_study_run_dir(request, name, run_id)
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
    study_run_dir = _resolve_study_run_dir(request, name, run_id)
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
    study_run_dir = _resolve_study_run_dir(request, name, run_id)
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
async def study_group_node_file(request: Request, name: str, run_id: str, label: str,
                                node_id: str, rel: str):
    study_run_dir = _resolve_study_run_dir(request, name, run_id)
    group_run_dir = _resolve_study_group_run_dir(study_run_dir, label)
    full = _safe_join(group_run_dir, rel)
    return FileResponse(str(full))


# ── study → group → subject drilldown ──────────────────────────────────


@router.get("/study-runs/{name}/{run_id}/group/{label}/subject/{sub}/graph")
async def study_group_subject_graph(request: Request, name: str, run_id: str,
                                    label: str, sub: str):
    """One subject's 7-stage graph inside one of a study's groups."""
    study_run_dir = _resolve_study_run_dir(request, name, run_id)
    group_run_dir = _resolve_study_group_run_dir(study_run_dir, label)
    group_summary = json.loads((group_run_dir / 'group_summary.json').read_text())
    for s in group_summary.get('subject_summaries') or []:
        if s.get('subject') == sub:
            graph = build_subject_graph(
                s.get('config_snapshot') or {},
                s.get('stages') or [],
                _registry(request),
            )
            sub_dir = group_run_dir / 'subjects' / sub
            return {
                'study_name': name,
                'run_id': run_id,
                'group_label': label,
                'group_name': group_summary.get('group_name', label),
                'subject': sub,
                'experiment': s.get('experiment', ''),
                'output_dir': str(sub_dir),
                **graph.to_dict(),
            }
    raise HTTPException(
        status_code=404,
        detail=(f"subject '{sub}' not in study {name}/{run_id} "
                f"group '{label}'"),
    )


@router.get("/study-runs/{name}/{run_id}/group/{label}/subject/{sub}/node/{node_id:path}/source")
async def study_group_subject_node_source(request: Request, name: str, run_id: str,
                                          label: str, sub: str, node_id: str):
    study_run_dir = _resolve_study_run_dir(request, name, run_id)
    group_run_dir = _resolve_study_group_run_dir(study_run_dir, label)
    group_summary = json.loads((group_run_dir / 'group_summary.json').read_text())
    for s in group_summary.get('subject_summaries') or []:
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
        detail=(f"subject '{sub}' not in study {name}/{run_id} "
                f"group '{label}'"),
    )


@router.get("/study-runs/{name}/{run_id}/group/{label}/subject/{sub}/node/{node_id:path}/outputs")
async def study_group_subject_node_outputs(request: Request, name: str, run_id: str,
                                           label: str, sub: str, node_id: str):
    study_run_dir = _resolve_study_run_dir(request, name, run_id)
    group_run_dir = _resolve_study_group_run_dir(study_run_dir, label)
    group_summary = json.loads((group_run_dir / 'group_summary.json').read_text())
    for s in group_summary.get('subject_summaries') or []:
        if s.get('subject') == sub:
            graph = build_subject_graph(
                s.get('config_snapshot') or {},
                s.get('stages') or [],
                _registry(request),
            ).to_dict()
            node = _find_node(graph, node_id)
            sub_dir = group_run_dir / 'subjects' / sub
            files = list_node_outputs(sub_dir, GraphNode(**{
                k: v for k, v in node.items() if k in GraphNode.__dataclass_fields__
            }))
            return {
                'node_id': node_id,
                'output_dir': str(sub_dir),
                'files': files,
            }
    raise HTTPException(
        status_code=404,
        detail=(f"subject '{sub}' not in study {name}/{run_id} "
                f"group '{label}'"),
    )


@router.get("/study-runs/{name}/{run_id}/group/{label}/subject/{sub}/node/{node_id:path}/file/{rel:path}")
async def study_group_subject_node_file(request: Request, name: str, run_id: str,
                                        label: str, sub: str, node_id: str, rel: str):
    study_run_dir = _resolve_study_run_dir(request, name, run_id)
    group_run_dir = _resolve_study_group_run_dir(study_run_dir, label)
    sub_dir = group_run_dir / 'subjects' / sub
    full = _safe_join(sub_dir, rel)
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
        label_to_name = _study_label_to_group_name(cfg, events)
        summary = {
            'config_snapshot': cfg,
            'study_stages': _events_to_study_stages(events),
            'group_summaries': _events_to_group_summaries(
                events, labels, label_to_group_name=label_to_name),
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


# ── in-flight drilldown into one of a live study's groups ──────────────


def _study_label_to_group_name(cfg: dict,
                               events: list[dict] | None = None) -> dict[str, str]:
    """Map each study-scope label (``groups[i].name``) to that group's
    internal ``group:`` name.

    Tries two sources in order:

    1. ``groups[i].config_snapshot.group`` if the study config carries
       inlined snapshots (finished study runs do).
    2. ``study_group_start`` / ``group_started`` events from the live
       stream — both carry ``group_label`` + ``group_name``. In-flight
       study handles only have the raw config (paths to group YAMLs,
       no snapshots), so this fallback is the one that matters for
       live runs.

    The mapping extends the event-stream group filter so subject-
    emitted events (which only carry the internal group name — the
    study's ``event_context`` doesn't cross the GroupOrchestrator's
    worker threads) still match the right study-scope group.
    """
    out: dict[str, str] = {}
    for entry in (cfg.get('groups') or []):
        if not isinstance(entry, dict):
            continue
        label = entry.get('name')
        if not isinstance(label, str) or not label:
            continue
        snapshot = entry.get('config_snapshot') or {}
        cand = snapshot.get('group') if isinstance(snapshot, dict) else None
        if isinstance(cand, str) and cand:
            out[label] = cand
    if events:
        for ev in events:
            ename = ev.get('event')
            label = ev.get('group_label')
            name = ev.get('group_name') or (
                ev.get('group') if ename == 'group_started' else None)
            if (label and name
                    and ename in ('study_group_start', 'group_started')):
                out.setdefault(label, str(name))
    return out


def _in_flight_study_group_summary(handle, label: str) -> dict:
    """Synthesize a partial GroupRunSummary for one group inside a live
    study. Filters the study's events down to the ones tagged with
    ``group`` / ``group_label`` == label (or the group's internal
    name — subject-emitted events from worker threads only carry the
    internal name) and folds them into the same shape the
    finished-study endpoints expect."""
    events = list(handle.events or [])
    cfg = handle.config or {}
    group_cfg: dict = {}
    # The group's internal name (e.g. ``modality_a_group``) lives
    # inside its referenced YAML; the study spec may store it inline
    # under ``config_snapshot.group`` or only ship the ``config:`` path.
    # We grab whichever is available.
    group_name: str | None = None
    for entry in cfg.get('groups', []) or []:
        if isinstance(entry, dict) and entry.get('name') == label:
            group_cfg = entry.get('config_snapshot') or {}
            cand = group_cfg.get('group') if isinstance(group_cfg, dict) else None
            if isinstance(cand, str) and cand:
                group_name = cand
            break
    # Fallback for live runs whose config doesn't inline a snapshot —
    # the orchestrator's wrapper events carry both names.
    if not group_name:
        mapping = _study_label_to_group_name(cfg, events)
        if mapping.get(label):
            group_name = mapping[label]

    accept = {label}
    if group_name:
        accept.add(group_name)
    group_events = [
        ev for ev in events
        if ev.get('group') in accept or ev.get('group_label') in accept
    ]
    return {
        'group_name': group_name or label,
        'subjects': cfg.get('subjects') or [],
        'started_at': '', 'finished_at': '', 'total_elapsed_s': 0.0,
        'group_stages': _events_to_group_stages(group_events),
        'subject_summaries': _events_to_subject_summaries(
            events, label,
            group_names=[group_name] if group_name else None,
        ),
        'config_snapshot': group_cfg,
        'run_id': '',
    }


def _resolve_in_flight_group_run_dir(handle, label: str) -> Path | None:
    """Best-effort: the live study writes each group to
    ``<study_run_dir>/groups/<label>/<latest>/``. Return that or None
    if the latest group run dir isn't on disk yet."""
    study_run_dir = _resolve_in_flight_output_dir(handle)
    if study_run_dir is None:
        return None
    group_root = study_run_dir / 'groups' / label
    if not group_root.is_dir():
        return None
    latest = group_root / 'latest'
    if latest.is_symlink() or latest.is_dir():
        try:
            return latest.resolve()
        except Exception:
            pass
    timestamped = sorted(
        (p for p in group_root.iterdir() if p.is_dir() and p.name != 'latest'),
        key=lambda p: p.stat().st_mtime, reverse=True,
    )
    return timestamped[0] if timestamped else None


@router.get("/runs/in-flight/{run_id}/group/{label}/graph")
async def in_flight_group_graph(request: Request, run_id: str, label: str):
    """Live group graph for one of an in-flight study's groups."""
    handle = _in_flight_handle(request, run_id)
    if not handle.is_study:
        raise HTTPException(
            status_code=404,
            detail=("in-flight run is not a study — "
                    "'group/{label}' drilldown is study-only"),
        )
    summary = _in_flight_study_group_summary(handle, label)
    graph = build_group_graph(summary, _registry(request))
    return {
        'run_id': run_id,
        'group_label': label,
        'group_name': summary['group_name'],
        'live': True,
        **graph.to_dict(),
    }


@router.get("/runs/in-flight/{run_id}/group/{label}/node/{node_id:path}/source")
async def in_flight_group_node_source(request: Request, run_id: str,
                                      label: str, node_id: str):
    handle = _in_flight_handle(request, run_id)
    if not handle.is_study:
        raise HTTPException(status_code=404, detail="study-only endpoint")
    summary = _in_flight_study_group_summary(handle, label)
    graph = build_group_graph(summary, _registry(request)).to_dict()
    node = _find_node(graph, node_id)
    if not node.get('source_path'):
        raise HTTPException(
            status_code=404,
            detail=f"No source registered for node '{node_id}'",
        )
    return _serve_source(node['source_path'])


@router.get("/runs/in-flight/{run_id}/group/{label}/node/{node_id:path}/outputs")
async def in_flight_group_node_outputs(request: Request, run_id: str,
                                       label: str, node_id: str):
    handle = _in_flight_handle(request, run_id)
    if not handle.is_study:
        raise HTTPException(status_code=404, detail="study-only endpoint")
    summary = _in_flight_study_group_summary(handle, label)
    graph = build_group_graph(summary, _registry(request)).to_dict()
    node = _find_node(graph, node_id)
    group_dir = _resolve_in_flight_group_run_dir(handle, label)
    files: list[dict] = []
    if group_dir is not None:
        files = list_node_outputs(group_dir, GraphNode(**{
            k: v for k, v in node.items() if k in GraphNode.__dataclass_fields__
        }))
    return {
        'node_id': node_id,
        'output_dir': str(group_dir) if group_dir else '',
        'files': files,
    }


@router.get("/runs/in-flight/{run_id}/group/{label}/node/{node_id:path}/file/{rel:path}")
async def in_flight_group_node_file(request: Request, run_id: str,
                                    label: str, node_id: str, rel: str):
    handle = _in_flight_handle(request, run_id)
    group_dir = _resolve_in_flight_group_run_dir(handle, label)
    if group_dir is None:
        raise HTTPException(
            status_code=404,
            detail=f"group dir not yet on disk for '{label}'",
        )
    full = _safe_join(group_dir, rel)
    return FileResponse(str(full))


# ── in-flight drilldown into one subject inside one group of a live study ──


def _in_flight_subject_in_group_graph(handle, label: str, sub: str,
                                      registry) -> dict:
    summary = _in_flight_study_group_summary(handle, label)
    for s in summary.get('subject_summaries') or []:
        if s.get('subject') == sub:
            return build_subject_graph(
                s.get('config_snapshot') or {},
                s.get('stages') or [],
                registry,
            ).to_dict()
    raise HTTPException(
        status_code=404,
        detail=(f"subject '{sub}' not yet recorded for group '{label}' "
                f"in live study run"),
    )


@router.get("/runs/in-flight/{run_id}/group/{label}/subject/{sub}/graph")
async def in_flight_group_subject_graph(request: Request, run_id: str,
                                        label: str, sub: str):
    handle = _in_flight_handle(request, run_id)
    if not handle.is_study:
        raise HTTPException(status_code=404, detail="study-only endpoint")
    graph = _in_flight_subject_in_group_graph(handle, label, sub, _registry(request))
    return {
        'run_id': run_id,
        'group_label': label,
        'subject': sub,
        'live': True,
        **graph,
    }


@router.get("/runs/in-flight/{run_id}/group/{label}/subject/{sub}/node/{node_id:path}/source")
async def in_flight_group_subject_node_source(request: Request, run_id: str,
                                              label: str, sub: str, node_id: str):
    handle = _in_flight_handle(request, run_id)
    if not handle.is_study:
        raise HTTPException(status_code=404, detail="study-only endpoint")
    graph = _in_flight_subject_in_group_graph(handle, label, sub, _registry(request))
    node = _find_node(graph, node_id)
    if not node.get('source_path'):
        raise HTTPException(
            status_code=404,
            detail=f"No source registered for node '{node_id}'",
        )
    return _serve_source(node['source_path'])


@router.get("/runs/in-flight/{run_id}/group/{label}/subject/{sub}/node/{node_id:path}/outputs")
async def in_flight_group_subject_node_outputs(request: Request, run_id: str,
                                               label: str, sub: str, node_id: str):
    handle = _in_flight_handle(request, run_id)
    if not handle.is_study:
        raise HTTPException(status_code=404, detail="study-only endpoint")
    graph = _in_flight_subject_in_group_graph(handle, label, sub, _registry(request))
    node = _find_node(graph, node_id)
    group_dir = _resolve_in_flight_group_run_dir(handle, label)
    sub_dir = group_dir / 'subjects' / sub if group_dir else None
    files: list[dict] = []
    if sub_dir is not None and sub_dir.is_dir():
        files = list_node_outputs(sub_dir, GraphNode(**{
            k: v for k, v in node.items() if k in GraphNode.__dataclass_fields__
        }))
    return {
        'node_id': node_id,
        'output_dir': str(sub_dir) if sub_dir else '',
        'files': files,
    }


@router.get("/runs/in-flight/{run_id}/group/{label}/subject/{sub}/node/{node_id:path}/file/{rel:path}")
async def in_flight_group_subject_node_file(request: Request, run_id: str,
                                            label: str, sub: str,
                                            node_id: str, rel: str):
    handle = _in_flight_handle(request, run_id)
    group_dir = _resolve_in_flight_group_run_dir(handle, label)
    if group_dir is None:
        raise HTTPException(
            status_code=404,
            detail=f"group dir not yet on disk for '{label}'",
        )
    sub_dir = group_dir / 'subjects' / sub
    if not sub_dir.is_dir():
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
        label_to_name = _study_label_to_group_name(cfg, events)
        summary = {
            'study_name': cfg.get('study') or '',
            'run_id': run_id,
            'group_labels': labels,
            'started_at': '', 'finished_at': '', 'total_elapsed_s': 0.0,
            'study_stages': _events_to_study_stages(events),
            'group_summaries': _events_to_group_summaries(
                events, labels, label_to_group_name=label_to_name),
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
