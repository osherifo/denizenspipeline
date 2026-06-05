"""Build a node-and-edge graph for a finished pipeline run.

Powers the "View graph" feature in the dashboard: given a
``RunSummary.config_snapshot`` (the YAML resolved at run time) plus the
:class:`ModuleRegistry`, produce a graph of plugin invocations that the
frontend can render the same way as the fmriprep DAG viewer.

A graph has two parts:

  * **nodes**: one per plugin invocation, plus one per pipeline stage
    (stage nodes act as the "wrapper" that the modal groups plugins
    under, mirroring fmriprep workflow nodes).
  * **edges**: linear between stages; within a stage, plugins live in
    parallel under the stage node.

The endpoints in :mod:`fmriflow.server.routes.run_graph` consume this.
"""

from __future__ import annotations

import inspect
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from fmriflow.registry import ModuleRegistry

logger = logging.getLogger(__name__)


# Map a node "kind" to the registry getter that resolves a plugin by
# name. Used to look up the source-file path for each invocation. Each
# entry takes the registry + plugin name and returns either an instance
# or a class (we tolerate both).
_GETTERS = {
    'stimulus_loader': lambda r, n: r.get_stimulus_loader(n),
    'response_loader': lambda r, n: r.get_response_loader(n),
    'feature_extractor': lambda r, n: r.get_feature_extractor(n),
    'feature_source': lambda r, n: r.get_feature_source(n),
    'preparer': lambda r, n: r.get_preparer(n),
    'preparation_step': lambda r, n: r.get_preparation_step(n),
    'model': lambda r, n: r.get_model(n),
    'analyzer': lambda r, n: r.get_analyzer(n),
    'reporter': lambda r, n: r.get_reporter(n),
    'group_analyzer': lambda r, n: r.get_group_analyzer(n),
    'group_reporter': lambda r, n: r.get_group_reporter(n),
}


@dataclass
class GraphNode:
    """One node in the run graph.

    For a stage node, ``kind == 'stage'`` and ``children`` is the list
    of plugin-node IDs underneath it. For a plugin node, ``kind`` is
    one of the keys in :data:`_GETTERS`.
    """
    id: str
    label: str
    kind: str
    stage: str
    status: str = 'unknown'        # ok / failed / warning / skipped / unknown
    elapsed_s: float | None = None
    detail: str = ''
    source_path: str | None = None  # absolute path on the server (read-only)
    plugin_name: str | None = None   # registry key (None for stage nodes)
    params: dict = field(default_factory=dict)
    children: list[str] = field(default_factory=list)
    # File paths recorded by the orchestrator (relative to output_dir
    # when possible). Empty for stages that didn't record, in which
    # case the outputs endpoint falls back to a name-substring scan.
    outputs: list[str] = field(default_factory=list)


@dataclass
class GraphEdge:
    source: str
    target: str


@dataclass
class RunGraph:
    nodes: list[GraphNode]
    edges: list[GraphEdge]

    def to_dict(self) -> dict:
        return {
            'nodes': [asdict(n) for n in self.nodes],
            'edges': [asdict(e) for e in self.edges],
        }


# ── plugin source resolution ───────────────────────────────────────────


def _plugin_source(registry: ModuleRegistry, kind: str,
                   name: str) -> str | None:
    """Return the file the plugin class is defined in, or None."""
    getter = _GETTERS.get(kind)
    if getter is None or not name:
        return None
    try:
        obj = getter(registry, name)
    except Exception as exc:
        logger.debug("Plugin lookup failed for %s/%s: %s", kind, name, exc)
        return None
    # The getters in ModuleRegistry return INSTANCES; the class is on
    # `__class__`. inspect.getfile works for both.
    try:
        return str(Path(inspect.getfile(type(obj))).resolve())
    except (TypeError, OSError):
        try:
            return str(Path(inspect.getfile(obj)).resolve())
        except Exception:
            return None


# ── subject (7-stage) graph ────────────────────────────────────────────


SUBJECT_STAGES = [
    ('stimuli', 'Stimuli'),
    ('responses', 'Responses'),
    ('features', 'Features'),
    ('prepare', 'Prepare'),
    ('model', 'Model'),
    ('analyze', 'Analyze'),
    ('report', 'Report'),
]


def _stage_status(stage_records: list, name: str) -> tuple[str, float | None, str]:
    """Lookup status / elapsed / detail for a stage from RunSummary records."""
    for s in stage_records or []:
        sname = s.get('name') if isinstance(s, dict) else getattr(s, 'name', None)
        if sname == name:
            if isinstance(s, dict):
                return (
                    s.get('status', 'unknown'),
                    s.get('elapsed_s'),
                    s.get('detail', '') or '',
                )
            return (
                getattr(s, 'status', 'unknown'),
                getattr(s, 'elapsed_s', None),
                getattr(s, 'detail', '') or '',
            )
    return ('unknown', None, '')


def _stage_recorded_nodes(stage_records: list, name: str) -> dict[str, dict]:
    """Return ``{node_id: {kind,name,status,elapsed_s,detail,outputs}}`` for
    one stage's recorded plugin invocations. Empty when the summary is
    older than the per-plugin schema.
    """
    out: dict[str, dict] = {}
    for s in stage_records or []:
        sname = s.get('name') if isinstance(s, dict) else getattr(s, 'name', None)
        if sname != name:
            continue
        raw = s.get('nodes') if isinstance(s, dict) else getattr(s, 'nodes', None)
        for n in raw or []:
            d = n if isinstance(n, dict) else {
                k: getattr(n, k, None) for k in
                ('id', 'kind', 'name', 'status', 'elapsed_s', 'detail', 'outputs')
            }
            nid = d.get('id') or ''
            if nid:
                out[nid] = d
    return out


def build_subject_graph(config_snapshot: dict, stage_records: list,
                        registry: ModuleRegistry) -> RunGraph:
    """Build the graph for one subject pipeline run.

    ``config_snapshot`` is the resolved subject YAML (with defaults
    merged in). ``stage_records`` is a list of StageRecord (or dicts) so
    each stage/plugin can be coloured by status.
    """
    cfg = config_snapshot or {}
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    stage_ids: list[str] = []

    for stage_key, stage_label in SUBJECT_STAGES:
        sid = f'stage:{stage_key}'
        status, elapsed, detail = _stage_status(stage_records, stage_key)
        recorded = _stage_recorded_nodes(stage_records, stage_key)
        plugin_nodes = _subject_plugin_nodes(cfg, stage_key, status, registry)
        _merge_recorded(plugin_nodes, recorded)

        nodes.append(GraphNode(
            id=sid, label=stage_label, kind='stage', stage=stage_key,
            status=status, elapsed_s=elapsed, detail=detail,
            children=[n.id for n in plugin_nodes],
        ))
        nodes.extend(plugin_nodes)
        stage_ids.append(sid)

    for a, b in zip(stage_ids, stage_ids[1:]):
        edges.append(GraphEdge(source=a, target=b))

    return RunGraph(nodes=nodes, edges=edges)


def _merge_recorded(plugin_nodes: list[GraphNode],
                    recorded: dict[str, dict]) -> None:
    """Overlay recorded per-plugin info onto config-derived plugin nodes.

    Recorded fields override the coarse "inherit stage status"
    approximation: status, elapsed_s, detail, outputs. The config-
    derived fields (label, kind, source_path, params) stay intact.

    Recorded nodes whose IDs don't match any config-derived node are
    appended at the end (covers a config edited between runs).
    """
    by_id = {n.id: n for n in plugin_nodes}
    for nid, rec in recorded.items():
        gn = by_id.get(nid)
        if gn is None:
            # Recorded but no config-derived equivalent — synthesize
            # a minimal node so the user still sees it.
            plugin_nodes.append(GraphNode(
                id=nid,
                label=str(rec.get('name') or nid),
                kind=str(rec.get('kind') or 'plugin'),
                stage=nid.split(':', 1)[0],
                status=str(rec.get('status') or 'unknown'),
                elapsed_s=rec.get('elapsed_s'),
                detail=str(rec.get('detail') or ''),
                plugin_name=rec.get('name'),
                outputs=list(rec.get('outputs') or []),
            ))
            continue
        gn.status = str(rec.get('status') or gn.status)
        es = rec.get('elapsed_s')
        if es is not None:
            gn.elapsed_s = es
        d = rec.get('detail')
        if d:
            gn.detail = str(d)
        gn.outputs = list(rec.get('outputs') or [])


def _subject_plugin_nodes(cfg: dict, stage: str, stage_status: str,
                          registry: ModuleRegistry) -> list[GraphNode]:
    """Resolve the plugin invocations declared in cfg for one stage."""
    items: list[tuple[str, str, dict]] = []
    # Each tuple: (plugin_kind, plugin_name, params_for_label)

    if stage == 'stimuli':
        loader = (cfg.get('stimulus') or {}).get('loader')
        if loader:
            items.append(('stimulus_loader', loader,
                          dict(cfg.get('stimulus') or {})))
    elif stage == 'responses':
        loader = (cfg.get('response') or {}).get('loader')
        if loader:
            items.append(('response_loader', loader,
                          dict(cfg.get('response') or {})))
    elif stage == 'features':
        for feat in cfg.get('features') or []:
            # Legacy schema: features may be a plain list of extractor
            # names (strings) rather than dicts.
            if isinstance(feat, str):
                items.append(('feature_extractor', feat, {}))
                continue
            if not isinstance(feat, dict):
                continue
            source = feat.get('source', 'compute')
            extractor = feat.get('extractor') or feat.get('name')
            # For 'compute' features we surface the extractor (that's the
            # interesting code path); other sources are just loaders.
            if source == 'compute' and extractor:
                items.append(('feature_extractor', extractor, dict(feat)))
            else:
                items.append(('feature_source', source, dict(feat)))
    elif stage == 'prepare':
        prep = cfg.get('preparation') or {}
        ptype = prep.get('type')
        if ptype:
            items.append(('preparer', ptype, dict(prep)))
        for step in prep.get('steps') or []:
            if isinstance(step, dict) and step.get('name'):
                items.append(('preparation_step', step['name'], dict(step)))
    elif stage == 'model':
        model = cfg.get('model') or {}
        mtype = model.get('type') if isinstance(model, dict) else None
        # Legacy schema: top-level `model_type: <str>` instead of model.type.
        if not mtype:
            mtype = cfg.get('model_type')
        if mtype:
            items.append(('model', mtype, dict(model) if isinstance(model, dict) else {}))
    elif stage == 'analyze':
        for acfg in cfg.get('analysis') or []:
            if isinstance(acfg, dict) and acfg.get('name'):
                items.append(('analyzer', acfg['name'], dict(acfg)))
    elif stage == 'report':
        reporting = cfg.get('reporting') or {}
        # New-style: reporting.reporters: [{name, params}, …]
        for rcfg in reporting.get('reporters') or []:
            if isinstance(rcfg, dict) and rcfg.get('name'):
                items.append(('reporter', rcfg['name'], dict(rcfg)))
        # Old-style: reporting.formats: [name, …]
        # Per-reporter params live under ``reporting.<name>`` in the
        # same block (e.g. ``reporting.r_flatmap: {cmap: magma, ...}``)
        # — fold them into the plugin node so the params tab in the
        # graph viewer shows what was actually configured instead of
        # an empty ``{}``.
        for fmt in reporting.get('formats') or []:
            if isinstance(fmt, str):
                params = reporting.get(fmt)
                items.append((
                    'reporter', fmt,
                    dict(params) if isinstance(params, dict) else {},
                ))

    out: list[GraphNode] = []
    seen: dict[str, int] = {}
    for kind, name, params in items:
        # Drop the noisy `name` field — already in label
        params = {k: v for k, v in params.items() if k != 'name'}
        # Suffix duplicate names within a stage (e.g. two `trim` steps).
        base_id = f'{stage}:{name}'
        n = seen.get(base_id, 0)
        seen[base_id] = n + 1
        node_id = base_id if n == 0 else f'{base_id}#{n + 1}'
        src = _plugin_source(registry, kind, name)
        out.append(GraphNode(
            id=node_id,
            label=name,
            kind=kind,
            stage=stage,
            # Stage-status fallback. When the run was made by the
            # post-NodeRecord orchestrator, _merge_recorded overlays
            # an accurate per-plugin status; legacy summaries fall
            # through to this approximation.
            status=stage_status,
            plugin_name=name,
            source_path=src,
            params=params,
        ))
    return out


# ── group graph ────────────────────────────────────────────────────────


GROUP_STAGE_LABELS = {
    'group_collect': 'Collect subjects',
    'subject_fanout': 'Subject fan-out',
    'group_analyze': 'Group analyze',
    'subject_second_pass': 'Subject second pass',
    'group_report': 'Group report',
}


def build_group_graph(group_summary: dict,
                      registry: ModuleRegistry) -> RunGraph:
    """Build a graph for one group run.

    ``group_summary`` is the GroupRunSummary as a dict (subject_summaries
    contain per-subject RunSummary). Returns a graph with one node per
    group stage, one per subject under ``subject_fanout``, and plugin
    children under ``group_analyze`` / ``group_report``.
    """
    cfg = group_summary.get('config_snapshot') or {}
    stage_records = group_summary.get('group_stages') or []
    subjects = group_summary.get('subject_summaries') or []

    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    stage_ids: list[str] = []

    # Stage order we render. subject_fanout doesn't get a StageRecord
    # but it's part of the conceptual flow, so we synthesize one between
    # group_collect and group_analyze.
    order = [
        'group_collect', 'subject_fanout', 'group_analyze',
        'subject_second_pass', 'group_report',
    ]
    has_second_pass = _group_has_second_pass(cfg, registry)
    has_analyze = bool(cfg.get('group_analyze'))
    has_report = bool(cfg.get('group_report'))

    for stage_key in order:
        # Skip stages the config didn't enable.
        if stage_key == 'group_analyze' and not has_analyze:
            continue
        if stage_key == 'subject_second_pass' and not has_second_pass:
            continue
        if stage_key == 'group_report' and not has_report:
            continue

        status, elapsed, detail = _stage_status(stage_records, stage_key)
        recorded = _stage_recorded_nodes(stage_records, stage_key)
        sid = f'stage:{stage_key}'
        children: list[str] = []
        # Track plugin nodes we add for this stage so _merge_recorded
        # can overlay them in place.
        stage_plugin_nodes: list[GraphNode] = []

        if stage_key == 'subject_fanout':
            for sub in subjects:
                sub_id = (sub.get('subject') if isinstance(sub, dict) else None) or ''
                if not sub_id:
                    continue
                sub_status = _subject_overall_status(sub)
                sub_nid = f'subject:{sub_id}'
                nodes.append(GraphNode(
                    id=sub_nid,
                    label=sub_id,
                    kind='subject',
                    stage='subject_fanout',
                    status=sub_status,
                    elapsed_s=sub.get('total_elapsed_s'),
                    plugin_name=sub_id,
                ))
                children.append(sub_nid)
            # Fall back: if no subjects in summary, just leave children
            # empty; the stage node still renders.
        elif stage_key == 'group_analyze':
            seen: dict[str, int] = {}
            for acfg in cfg.get('group_analyze') or []:
                if not (isinstance(acfg, dict) and acfg.get('name')):
                    continue
                name = acfg['name']
                src = _plugin_source(registry, 'group_analyzer', name)
                base_id = f'group_analyze:{name}'
                n_seen = seen.get(base_id, 0)
                seen[base_id] = n_seen + 1
                nid = base_id if n_seen == 0 else f'{base_id}#{n_seen + 1}'
                params = {k: v for k, v in acfg.items() if k != 'name'}
                stage_plugin_nodes.append(GraphNode(
                    id=nid, label=name, kind='group_analyzer',
                    stage='group_analyze', status=status, elapsed_s=None,
                    plugin_name=name, source_path=src, params=params,
                ))
                children.append(nid)
        elif stage_key == 'group_report':
            seen: dict[str, int] = {}
            for rcfg in cfg.get('group_report') or []:
                if not (isinstance(rcfg, dict) and rcfg.get('name')):
                    continue
                name = rcfg['name']
                src = _plugin_source(registry, 'group_reporter', name)
                base_id = f'group_report:{name}'
                n_seen = seen.get(base_id, 0)
                seen[base_id] = n_seen + 1
                nid = base_id if n_seen == 0 else f'{base_id}#{n_seen + 1}'
                params = {k: v for k, v in rcfg.items() if k != 'name'}
                stage_plugin_nodes.append(GraphNode(
                    id=nid, label=name, kind='group_reporter',
                    stage='group_report', status=status, elapsed_s=None,
                    plugin_name=name, source_path=src, params=params,
                ))
                children.append(nid)

        # Overlay recorded per-plugin info (group runs from the v2
        # orchestrator carry NodeRecords).
        if stage_plugin_nodes:
            _merge_recorded(stage_plugin_nodes, recorded)
            children = [n.id for n in stage_plugin_nodes]
            nodes.extend(stage_plugin_nodes)

        nodes.insert(
            # Insert the stage node BEFORE its children so iteration
            # order matches visual order. The simplest way: build the
            # children first (already done) then append.
            len(nodes) - len(children),
            GraphNode(
                id=sid, label=GROUP_STAGE_LABELS.get(stage_key, stage_key),
                kind='stage', stage=stage_key,
                status=status, elapsed_s=elapsed, detail=detail,
                children=children,
            ),
        )
        stage_ids.append(sid)

    for a, b in zip(stage_ids, stage_ids[1:]):
        edges.append(GraphEdge(source=a, target=b))

    return RunGraph(nodes=nodes, edges=edges)


# ── study graph ────────────────────────────────────────────────────────


STUDY_STAGE_LABELS = {
    'study_collect': 'Collect groups',
    'groups_fanout': 'Groups fan-out',
    'study_analyze': 'Study analyze',
    'study_report': 'Study report',
}


def build_study_graph(study_summary: dict,
                      registry: ModuleRegistry) -> RunGraph:
    """Build a graph for one study run.

    Same shape as :func:`build_group_graph` one scope up: stage chain
    ``study_collect → groups_fanout → study_analyze → study_report``,
    with M ``group:<label>`` child nodes under ``groups_fanout`` and
    plugin children under analyze/report. Recorded NodeRecords from
    StageRecord.nodes overlay accurate per-plugin status + outputs.
    """
    cfg = study_summary.get('config_snapshot') or {}
    stage_records = study_summary.get('study_stages') or []
    group_summaries = study_summary.get('group_summaries') or []
    group_labels = study_summary.get('group_labels') or []

    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    stage_ids: list[str] = []

    has_analyze = bool(cfg.get('study_analyze'))
    has_report = bool(cfg.get('study_report'))
    order = ['study_collect', 'groups_fanout', 'study_analyze', 'study_report']

    for stage_key in order:
        if stage_key == 'study_analyze' and not has_analyze:
            continue
        if stage_key == 'study_report' and not has_report:
            continue

        status, elapsed, detail = _stage_status(stage_records, stage_key)
        recorded = _stage_recorded_nodes(stage_records, stage_key)
        sid = f'stage:{stage_key}'
        children: list[str] = []
        stage_plugin_nodes: list[GraphNode] = []

        if stage_key == 'groups_fanout':
            # One node per group; label by study-scope label (preferred)
            # falling back to the underlying group_name. Status rolled up
            # from that group's subject statuses.
            for i, label in enumerate(group_labels):
                gs = group_summaries[i] if i < len(group_summaries) else None
                gstatus = _group_overall_status(gs)
                elapsed_g = gs.get('total_elapsed_s') if isinstance(gs, dict) else None
                gname = gs.get('group_name') if isinstance(gs, dict) else None
                gnid = f'group:{label}'
                nodes.append(GraphNode(
                    id=gnid,
                    label=label,
                    kind='group',
                    stage='groups_fanout',
                    status=gstatus,
                    elapsed_s=elapsed_g,
                    detail=str(gname or ''),
                    plugin_name=label,
                ))
                children.append(gnid)
        elif stage_key == 'study_analyze':
            seen: dict[str, int] = {}
            for acfg in cfg.get('study_analyze') or []:
                if not (isinstance(acfg, dict) and acfg.get('name')):
                    continue
                name = acfg['name']
                src = _plugin_source(registry, 'study_analyzer', name)
                base_id = f'study_analyze:{name}'
                n_seen = seen.get(base_id, 0)
                seen[base_id] = n_seen + 1
                nid = base_id if n_seen == 0 else f'{base_id}#{n_seen + 1}'
                params = {k: v for k, v in acfg.items() if k != 'name'}
                stage_plugin_nodes.append(GraphNode(
                    id=nid, label=name, kind='study_analyzer',
                    stage='study_analyze', status=status, elapsed_s=None,
                    plugin_name=name, source_path=src, params=params,
                ))
                children.append(nid)
        elif stage_key == 'study_report':
            seen: dict[str, int] = {}
            for rcfg in cfg.get('study_report') or []:
                if not (isinstance(rcfg, dict) and rcfg.get('name')):
                    continue
                name = rcfg['name']
                src = _plugin_source(registry, 'study_reporter', name)
                base_id = f'study_report:{name}'
                n_seen = seen.get(base_id, 0)
                seen[base_id] = n_seen + 1
                nid = base_id if n_seen == 0 else f'{base_id}#{n_seen + 1}'
                params = {k: v for k, v in rcfg.items() if k != 'name'}
                stage_plugin_nodes.append(GraphNode(
                    id=nid, label=name, kind='study_reporter',
                    stage='study_report', status=status, elapsed_s=None,
                    plugin_name=name, source_path=src, params=params,
                ))
                children.append(nid)

        if stage_plugin_nodes:
            _merge_recorded(stage_plugin_nodes, recorded)
            children = [n.id for n in stage_plugin_nodes]
            nodes.extend(stage_plugin_nodes)

        nodes.insert(
            len(nodes) - len(children),
            GraphNode(
                id=sid, label=STUDY_STAGE_LABELS.get(stage_key, stage_key),
                kind='stage', stage=stage_key,
                status=status, elapsed_s=elapsed, detail=detail,
                children=children,
            ),
        )
        stage_ids.append(sid)

    for a, b in zip(stage_ids, stage_ids[1:]):
        edges.append(GraphEdge(source=a, target=b))

    return RunGraph(nodes=nodes, edges=edges)


def _group_overall_status(gs: Any) -> str:
    """Coarse pass/fail for a group's GroupRunSummary dict, rolled up
    across its subjects.

    Honors a pre-computed ``status`` field on the dict first — that's
    how the in-flight study graph signals "this group is running right
    now" before any subject has finished a stage. Falls back to the
    per-subject rollup for finished runs.
    """
    if not isinstance(gs, dict):
        return 'unknown'
    explicit = gs.get('status')
    if explicit in ('running', 'failed', 'warning'):
        return explicit
    subjects = gs.get('subject_summaries') or []
    if not subjects:
        # ``status='ok'`` on a finished group with no subject records
        # (edge case) is still useful; defer to the explicit value if
        # set, otherwise fall through to 'unknown'.
        return explicit if explicit == 'ok' else 'unknown'
    status = 'ok'
    for sub in subjects:
        sub_st = _subject_overall_status(sub)
        if sub_st == 'failed':
            return 'failed'
        if sub_st == 'warning':
            status = 'warning'
    return status


def _group_has_second_pass(cfg: dict, registry: ModuleRegistry) -> bool:
    """True iff any configured group analyzer produces a subject artifact."""
    for acfg in cfg.get('group_analyze') or []:
        if not (isinstance(acfg, dict) and acfg.get('name')):
            continue
        try:
            ga = registry.get_group_analyzer(acfg['name'])
        except Exception:
            continue
        if getattr(ga, 'produces_subject_artifact', False):
            return True
    return False


def _subject_overall_status(sub: Any) -> str:
    """Coarse pass/fail for a per-subject RunSummary dict.

    Honors an explicit ``status`` field first — that's how the
    in-flight group / study graph signals "this subject is running
    right now" (or has just been marked failed by its
    ``group_subject_done`` event) before the per-stage events catch
    up. Falls back to rolling up the per-stage status list for
    finished runs.
    """
    if not isinstance(sub, dict):
        return 'unknown'
    explicit = sub.get('status')
    if explicit in ('running', 'failed', 'warning'):
        return explicit
    stages = sub.get('stages') or []
    status = 'ok'
    for s in stages:
        sst = s.get('status') if isinstance(s, dict) else None
        if sst == 'failed':
            return 'failed'
        if sst == 'warning':
            status = 'warning'
    if not stages:
        return explicit if explicit == 'ok' else 'unknown'
    return status


# ── source code + outputs ──────────────────────────────────────────────


def read_source(source_path: str) -> str:
    """Return the file's text. Caller is responsible for validating path."""
    return Path(source_path).read_text(encoding='utf-8', errors='replace')


def list_node_outputs(output_dir: Path, node: GraphNode) -> list[dict]:
    """List output files attributable to one node.

    Authoritative path: ``node.outputs`` (populated by the orchestrator
    via :class:`NodeRecord`). When recorded outputs are present, list
    those files with stat info — no guessing required.

    Fallback: name-substring scan of ``output_dir``. Older runs from
    before per-plugin tracking get the old heuristic; the new ones get
    accurate attribution.
    """
    if not output_dir.is_dir():
        return []
    files: list[dict] = []
    # 1. Recorded outputs — authoritative, accurate.
    if node.outputs:
        for rel in node.outputs:
            full = output_dir / rel if not Path(rel).is_absolute() else Path(rel)
            if not full.is_file():
                continue
            try:
                stat = full.stat()
            except OSError:
                continue
            files.append({
                'name': full.name,
                'rel': rel,
                'size': stat.st_size,
                'suffix': full.suffix.lower(),
            })
        return files

    # 2. Fallback heuristic for runs that pre-date NodeRecord tracking.
    is_stage = node.kind == 'stage'
    name = (node.plugin_name or '').lower()
    for entry in sorted(output_dir.iterdir()):
        if not entry.is_file():
            continue
        if entry.name in ('run_summary.json', 'pipeline.log'):
            continue
        if not is_stage:
            if not name or name not in entry.name.lower():
                continue
        stat = entry.stat()
        files.append({
            'name': entry.name,
            'rel': entry.name,
            'size': stat.st_size,
            'suffix': entry.suffix.lower(),
        })
    return files
