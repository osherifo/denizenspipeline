"""Stage-based subject configs compile into equivalent graphs."""

from __future__ import annotations

import pytest

from fmriflow.analysis.catalog import NodeCatalog
from fmriflow.analysis.compile_legacy import compile_subject_config
from fmriflow.analysis.graph import AnalysisGraph
from fmriflow.core.stages import SUBJECT_STAGES
from fmriflow.exceptions import ConfigError
from tests.test_integration.test_pipeline import _make_config, _make_registry


def test_node_ids_match_the_stage_orchestrator_and_the_graph_validates():
    g = compile_subject_config(_make_config())
    assert [n.id for n in g.nodes] == [
        "stimuli:mock_stim", "responses:mock_resp", "features:mock_source", "utility:bundle_features",
        "prepare:mock_prep", "model:mock_model", "utility:collect_context", "report:mock_report"]
    assert g.stages == list(SUBJECT_STAGES) and g.globals == _make_config() and g.scope == "subject"
    assert g.validate(NodeCatalog(_make_registry()).discover()) == []


def test_compute_feature_params():
    cfg = _make_config()
    cfg["features"] = [{"name": "renamed", "extractor": "numwords", "params": {"a": 1},
                        "save_to": {"backend": "filesystem", "path": "/x"}, "extra": 2},
                       {"name": "english1000"}]
    g = compile_subject_config(cfg)
    first, second = g.node("features:numwords"), g.node("features:english1000")
    assert first.type == "feature_extractor:numwords"
    assert first.params == {"a": 1, "feature_name": "renamed",
                            "save_to": {"backend": "filesystem", "path": "/x"}, "_section": {"extra": 2}}
    assert second.type == "feature_extractor:english1000" and second.params == {}


def test_source_feature_model_and_analyzer_params():
    cfg = _make_config()
    cfg["features"] = [{"name": "letters", "source": "grouped_hdf", "path": "/f.hdf", "key": "letters"}]
    cfg["model"] = {"type": "banded_ridge", "params": {"alphas": [1, 10]}, "delays": [1, 2]}
    cfg["analysis"] = [{"name": "project_to_fsaverage", "params": {"input_key": "result.scores"}, "note": "x"}]
    g = compile_subject_config(cfg)
    assert g.node("features:grouped_hdf").params == {"path": "/f.hdf", "key": "letters", "feature_name": "letters"}
    assert g.node("model:banded_ridge").params == {"alphas": [1, 10], "_section": {"delays": [1, 2]}}
    assert g.node("analyze:project_to_fsaverage").params == {"input_key": "result.scores", "_section": {"note": "x"}}


def test_analyzers_chain_and_every_reporter_follows_the_last_one():
    cfg = _make_config()
    cfg["analysis"] = [{"name": "a1"}, {"name": "a2"}]
    cfg["reporting"] = {"formats": ["flatmap", "flatmap", "metrics"], "flatmap": {"cmap": "magma"},
                        "output_dir": "/tmp/x"}
    g = compile_subject_config(cfg)
    feeds = {(e.source, e.target) for e in g.edges}
    assert ("utility:collect_context", "analyze:a1") in feeds and ("analyze:a1", "analyze:a2") in feeds
    assert {t for s, t in feeds if s == "analyze:a2"} == {"report:flatmap", "report:flatmap#2", "report:metrics"}
    assert g.node("report:flatmap#2").params == {"cmap": "magma"}


def test_duplicate_analyzers_are_rejected_like_the_stage_orchestrator():
    cfg = _make_config()
    cfg["analysis"] = [{"name": "dup"}, {"name": "dup"}]
    with pytest.raises(ConfigError):
        compile_subject_config(cfg)


def test_compiled_graph_round_trips():
    g = compile_subject_config(_make_config())
    assert AnalysisGraph.from_yaml(g.to_yaml()).to_dict() == g.to_dict()
