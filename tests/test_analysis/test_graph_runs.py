"""Graph-native subject runs: input binding, the shared graph check, bundled
templates, the saved-graph store, graph YAML in the config browser, and the
engine default."""

from __future__ import annotations

import pytest
import yaml

from fmriflow.analysis.catalog import NodeCatalog
from fmriflow.analysis.executor import check_graph, resolve_graph_inputs
from fmriflow.analysis.graph import AnalysisGraph
from fmriflow.analysis.templates import (
    delete_user_template, list_templates, load_template, save_user_template, template_names,
)
from fmriflow.exceptions import ConfigError
from fmriflow.registry import ModuleRegistry
from fmriflow.server.services.analysis_graph_store import AnalysisGraphStore, is_graph_document
from fmriflow.server.services.config_store import ConfigStore


@pytest.fixture(scope="module")
def catalog():
    registry = ModuleRegistry()
    registry.discover()
    return NodeCatalog(registry).discover()


def _graph(**extra) -> AnalysisGraph:
    doc = {
        "name": "g",
        "inputs": {"subject": {"kind": "str"},
                   "out": {"kind": "dir", "required": False, "default": "/tmp/out"},
                   "note": {"kind": "str", "required": False}},
        "globals": {"subject": "$inputs.subject", "reporting": {"output_dir": "$inputs.out"}},
        "nodes": [{"id": "m", "type": "stimulus_loader:skip",
                   "data": {"params": {"tags": ["$inputs.subject", "fixed"], "note": "$inputs.note"}}}],
        "edges": [],
    }
    doc.update(extra)
    return AnalysisGraph.from_dict(doc)


# ── input binding ───────────────────────────────────────────────────


def test_inputs_bind_globals_and_params_with_defaults():
    bound, resolved = resolve_graph_inputs(_graph(), {"subject": "sub01"})
    assert bound.globals == {"subject": "sub01", "reporting": {"output_dir": "/tmp/out"}}
    assert bound.nodes[0].params == {"tags": ["sub01", "fixed"], "note": None}
    assert resolved == {"subject": "sub01", "out": "/tmp/out"}


def test_binding_leaves_the_template_untouched():
    graph = _graph()
    resolve_graph_inputs(graph, {"subject": "sub01"})
    assert graph.globals["subject"] == "$inputs.subject"


def test_missing_required_input_is_an_error():
    with pytest.raises(ConfigError) as exc:
        resolve_graph_inputs(_graph(), {})
    assert any("'subject' needs a value" in e for e in exc.value.errors)


def test_undeclared_input_reference_is_an_error():
    graph = _graph(globals={"subject": "$inputs.subjekt"})
    with pytest.raises(ConfigError) as exc:
        resolve_graph_inputs(graph, {"subject": "sub01"})
    assert any("subjekt" in e for e in exc.value.errors)


def test_check_graph_uses_saved_run_inputs(catalog):
    graph = _graph()
    assert any("needs a value" in e for e in check_graph(graph, catalog))
    graph.run_defaults = {"inputs": {"subject": "sub01"}}
    assert not any("needs a value" in e for e in check_graph(graph, catalog))


def test_yaml_has_no_anchors():
    shared = [1, 2, 3]
    graph = _graph(globals={"a": shared, "b": shared})
    text = graph.to_yaml()
    assert "&id" not in text and "*id" not in text
    assert yaml.safe_load(text)["globals"] == {"a": [1, 2, 3], "b": [1, 2, 3]}


# ── bundled templates ───────────────────────────────────────────────


def test_bundled_templates_exist():
    assert {"analyze", "analyze_precomputed_features"} <= set(template_names())


@pytest.mark.parametrize("name", ["analyze", "analyze_precomputed_features"])
def test_bundled_template_is_valid_and_portable(name, catalog):
    from fmriflow.graph.templates import concrete_path_warnings

    graph = load_template(name)
    assert graph.scope == "subject"
    assert graph.validate(catalog) == []
    assert concrete_path_warnings(graph) == []
    values = {k: ["run1"] if k == "test_runs" else f"value_{k}" for k in graph.inputs}
    bound, _ = resolve_graph_inputs(graph, values)
    assert "$inputs." not in bound.to_yaml()


def test_user_templates_save_list_and_delete(monkeypatch, tmp_path):
    monkeypatch.setenv("FMRIFLOW_HOME", str(tmp_path))
    graph = load_template("analyze")
    graph.run_defaults = {"inputs": {"subject": "sub01"}}
    path = save_user_template("my_analyze", graph)
    assert path.parent == tmp_path / "addons" / "analysis_pipelines"
    rows = {r["name"]: r for r in list_templates()}
    assert rows["my_analyze"]["tier"] == "user" and rows["my_analyze"]["scope"] == "subject"
    assert load_template("my_analyze").run_defaults == {}
    with pytest.raises(ValueError):
        save_user_template("analyze", graph)
    assert delete_user_template("my_analyze") is True
    assert "my_analyze" not in template_names()


# ── saved graphs ────────────────────────────────────────────────────


def test_graph_store_round_trip(tmp_path):
    store = AnalysisGraphStore(tmp_path)
    store.save("mine", _graph())
    (tmp_path / "stage.yaml").write_text("experiment: e\nsubject: s\n")
    assert [r["name"] for r in store.list_graphs()] == ["mine"]
    assert store.load("mine").globals["subject"] == "$inputs.subject"
    with pytest.raises(KeyError):
        store.load("stage")
    with pytest.raises(ValueError):
        store.save("stage", _graph())
    with pytest.raises(ValueError):
        store.delete("stage")
    assert store.delete("mine") is True and store.delete("mine") is False


def test_graph_document_detection():
    assert is_graph_document({"nodes": []})
    assert is_graph_document({"graph": {"nodes": []}})
    assert not is_graph_document({"experiment": "e"})


def test_config_browser_lists_graphs(tmp_path):
    root = tmp_path / "analysis"
    root.mkdir()
    graph = _graph()
    graph.run_defaults = {"inputs": {"subject": "sub01", "out": "/tmp/results"}}
    graph.save(root / "graph_config.yaml")
    store = ConfigStore(root)
    row = next(c for c in store.list_configs() if c.filename == "graph_config.yaml")
    assert (row.format, row.kind, row.subject, row.output_dir) == ("graph", "subject", "sub01", "/tmp/results")
    assert row.experiment == "g"


def test_config_browser_validates_graphs(tmp_path, catalog):
    root = tmp_path / "analysis"
    root.mkdir()
    _graph().save(root / "graph_config.yaml")
    result = ConfigStore(root).validate_config("graph_config.yaml", registry=catalog.registry
                                               if hasattr(catalog, "registry") else None)
    assert not result["valid"]
    assert any("needs a value" in e for e in result["errors"])


# ── engine default ──────────────────────────────────────────────────


def test_default_engine_is_graph(monkeypatch):
    from fmriflow.pipeline import resolve_engine

    monkeypatch.delenv("FMRIFLOW_ENGINE", raising=False)
    assert resolve_engine() == "graph"
    monkeypatch.setenv("FMRIFLOW_ENGINE", "legacy")
    assert resolve_engine() == "legacy"
    assert resolve_engine("graph") == "graph"
