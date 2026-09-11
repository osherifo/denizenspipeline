"""Compile a stage-based subject config into an analysis graph.

The graph reproduces the fixed seven-stage pipeline exactly: node ids are the
ids the stage orchestrator records (``features:english1000``,
``report:flatmap#2``), the resolved config becomes the graph globals so
modules reading other sections keep working, and each node's params are its
share of its section.

Wiring::

    stimuli ─┬─> feature nodes ─> bundle ─┐
    responses┴──────────────────────────> preparer ─> model
    all stage outputs ─> collect_context ─> analyzer ─> analyzer ... ─> each reporter
"""

from __future__ import annotations

import copy
from typing import Any

from fmriflow.analysis.adapters import SECTION_PARAM
from fmriflow.analysis.graph import AnalysisGraph, AnalysisNode
from fmriflow.core.run_summary import NodeIdGen
from fmriflow.core.stages import SUBJECT_STAGES
from fmriflow.exceptions import ConfigError
from fmriflow.graph.model import EdgeSpec

BUNDLE_ID = "utility:bundle_features"
CONTEXT_ID = "utility:collect_context"

_COLUMN = {stage: i for i, stage in enumerate(SUBJECT_STAGES)}


class _Builder:
    def __init__(self) -> None:
        self.nodes: list[AnalysisNode] = []
        self.edges: list[EdgeSpec] = []
        self._rows: dict[int, int] = {}

    def node(self, node_id: str, node_type: str, params: dict, column: int) -> str:
        row = self._rows.get(column, 0)
        self._rows[column] = row + 1
        self.nodes.append(AnalysisNode(id=node_id, type=node_type, params=params,
                                       position={"x": 60.0 + 280.0 * column, "y": 60.0 + 130.0 * row}))
        return node_id

    def edge(self, source: str, source_handle: str, target: str, target_handle: str) -> None:
        self.edges.append(EdgeSpec(id=f"e{len(self.edges) + 1}", source=source, target=target,
                                   source_handle=source_handle, target_handle=target_handle))


def compile_subject_config(config: dict[str, Any], *, name: str | None = None) -> AnalysisGraph:
    """Graph equivalent of a resolved subject config (as :func:`load_config` returns)."""
    cfg = copy.deepcopy(config)
    b = _Builder()

    stim_cfg = dict(cfg.get("stimulus") or {})
    loader = stim_cfg.pop("loader", "textgrid")
    stim = b.node(NodeIdGen("stimuli").make(loader), f"stimulus_loader:{loader}", stim_cfg, _COLUMN["stimuli"])

    resp_cfg = dict(cfg.get("response") or {})
    rloader = resp_cfg.pop("loader", "cloud")
    resp = b.node(NodeIdGen("responses").make(rloader), f"response_loader:{rloader}", resp_cfg, _COLUMN["responses"])

    feature_ids = NodeIdGen("features")
    features: list[str] = []
    for feat in cfg.get("features", []) or []:
        feat = dict(feat)
        feature_name = feat.get("name")
        source = feat.get("source", "compute")
        if source == "compute":
            extractor = feat.get("extractor", feature_name)
            params = dict(feat.get("params") or {})
            if feature_name and feature_name != extractor:
                params["feature_name"] = feature_name
            if feat.get("save_to"):
                params["save_to"] = feat["save_to"]
            section = {k: v for k, v in feat.items() if k not in ("name", "source", "extractor", "params", "save_to")}
            if section:
                params[SECTION_PARAM] = section
            node_id, node_type = feature_ids.make(extractor), f"feature_extractor:{extractor}"
        else:
            params = {k: v for k, v in feat.items() if k not in ("name", "source")}
            params["feature_name"] = feature_name
            node_id, node_type = feature_ids.make(source), f"feature_source:{source}"
        features.append(b.node(node_id, node_type, params, _COLUMN["features"]))
        b.edge(stim, "stimuli", node_id, "stimuli")
        b.edge(resp, "responses", node_id, "responses")

    bundle = b.node(BUNDLE_ID, "utility:bundle_features", {}, _COLUMN["features"])
    for feature in features:
        b.edge(feature, "feature", bundle, "features")

    prep_cfg = cfg.get("preparation") or {}
    ptype = prep_cfg.get("type", "default") if isinstance(prep_cfg, dict) else "default"
    prep_params = {k: v for k, v in prep_cfg.items() if k != "type"} if isinstance(prep_cfg, dict) else {}
    prep = b.node(NodeIdGen("prepare").make(ptype), f"preparer:{ptype}", prep_params, _COLUMN["prepare"])
    b.edge(resp, "responses", prep, "responses")
    b.edge(bundle, "features", prep, "features")

    model_cfg = dict(cfg.get("model") or {})
    mtype = model_cfg.pop("type", "bootstrap_ridge")
    model_params = dict(model_cfg.pop("params", {}) or {})
    if model_cfg:
        model_params[SECTION_PARAM] = model_cfg
    model = b.node(NodeIdGen("model").make(mtype), f"model:{mtype}", model_params, _COLUMN["model"])
    b.edge(prep, "prepared", model, "prepared")

    context = b.node(CONTEXT_ID, "utility:collect_context", {}, _COLUMN["analyze"])
    for src, port in ((stim, "stimuli"), (resp, "responses"), (bundle, "features"),
                      (prep, "prepared"), (model, "result")):
        b.edge(src, port, context, port)

    last = context
    analyzer_ids = NodeIdGen("analyze")
    seen: set[str] = set()
    for acfg in cfg.get("analysis", []) or []:
        aname = acfg["name"]
        if aname in seen:
            raise ConfigError(
                f"Duplicate analyzer name '{aname}' in 'analysis' configuration; "
                "analyzer names must be unique.")
        seen.add(aname)
        params = dict(acfg.get("params") or {})
        section = {k: v for k, v in acfg.items() if k not in ("name", "params")}
        if section:
            params[SECTION_PARAM] = section
        node = b.node(analyzer_ids.make(aname), f"analyzer:{aname}", params, _COLUMN["analyze"])
        b.edge(last, "context", node, "context")
        last = node

    reporting = cfg.get("reporting") or {}
    reporter_ids = NodeIdGen("report")
    for fmt in reporting.get("formats", ["metrics"]):
        opts = reporting.get(fmt)
        node = b.node(reporter_ids.make(fmt), f"reporter:{fmt}", dict(opts) if isinstance(opts, dict) else {},
                      _COLUMN["report"])
        b.edge(last, "context", node, "context")

    return AnalysisGraph(
        name=name or str(cfg.get("experiment") or "untitled"),
        description="Compiled from a stage-based subject config",
        scope="subject",
        globals=cfg,
        stages=list(SUBJECT_STAGES),
        nodes=b.nodes,
        edges=b.edges,
    )
