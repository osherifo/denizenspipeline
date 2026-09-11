"""Analysis graph model: serialisation, type checks, required inputs."""

from __future__ import annotations

from fmriflow.analysis.catalog import NodeCatalog
from fmriflow.analysis.graph import AnalysisGraph, AnalysisNode
from fmriflow.graph import EdgeSpec


def _graph(**kw):
    return AnalysisGraph(
        name="g", scope=kw.pop("scope", "subject"), globals={"subject": "sub01"}, stages=["stimuli"],
        nodes=[AnalysisNode(id="s", type="stimulus_loader:textgrid", params={"language": "en"})], **kw)


def test_roundtrip_keeps_scope_globals_and_stages():
    g = _graph()
    d = g.to_dict()
    assert d["scope"] == "subject" and d["globals"] == {"subject": "sub01"} and d["stages"] == ["stimuli"]
    assert AnalysisGraph.from_yaml(g.to_yaml()).to_dict() == d
    wrapped = "graph:\n" + "".join("  " + line + "\n" for line in g.to_yaml().splitlines())
    assert AnalysisGraph.from_yaml(wrapped).to_dict() == d


def test_incompatible_port_types_are_rejected():
    cat = NodeCatalog().discover()
    g = AnalysisGraph(
        nodes=[AnalysisNode(id="s", type="stimulus_loader:textgrid"), AnalysisNode(id="m", type="model:bootstrap_ridge")],
        edges=[EdgeSpec(id="e1", source="s", target="m", source_handle="stimuli", target_handle="prepared")])
    errors = g.validate(cat)
    assert any("s.stimuli (StimulusData) cannot feed m.prepared (PreparedData)" in e for e in errors)


def test_required_inputs_must_be_connected():
    cat = NodeCatalog().discover()
    g = AnalysisGraph(nodes=[AnalysisNode(id="m", type="model:bootstrap_ridge")])
    assert "node m: required input 'prepared' is not connected" in g.validate(cat)


def test_unknown_scope_is_reported():
    assert any("unknown scope" in e for e in _graph(scope="cohort").validate(None))
