"""Every analysis module becomes a typed node type."""

from __future__ import annotations

from fmriflow.analysis.adapters import CATEGORY_ADAPTERS
from fmriflow.analysis.catalog import NodeCatalog
from fmriflow.analysis.port_types import LATTICE
from fmriflow.graph import EdgeSpec, GraphSpec, NodeSpec, port_type
from fmriflow.modules._decorators import _reporters
from fmriflow.modules.user_modules import discover_user_modules


def _catalog():
    return NodeCatalog().discover()


def test_every_registered_module_is_a_node():
    cat = _catalog()
    reg = cat.registry
    for category, names in reg.list_modules().items():
        if category in ("response_readers", "preparation_steps"):
            continue  # parameters of their loader / preparer, not nodes
        prefix = CATEGORY_ADAPTERS[category].prefix
        for name in names:
            assert cat.has(f"{prefix}:{name}"), f"{category}/{name}"
    for stage, names in reg.list_qa_reporters().items():
        for name in names:
            assert cat.has(f"qa_reporter:{stage}.{name}")


def test_type_ids_are_qualified_and_unique():
    infos = _catalog().list(include_hidden=True)
    ids = [i.type for i in infos]
    assert len(ids) == len(set(ids))
    assert all(":" in t for t in ids)
    assert {"stimulus_loader:nsd", "response_loader:nsd"} <= set(ids)


def test_compute_source_is_hidden_from_the_palette():
    cat = _catalog()
    assert cat.info("feature_source:compute").hidden
    assert "feature_source:compute" not in {i.type for i in cat.list()}


def test_every_port_type_is_known():
    for info in _catalog().list(include_hidden=True):
        for spec in (*info.inputs.values(), *info.outputs.values()):
            assert LATTICE.has(port_type(spec)), (info.type, spec)


def test_group_bindings_port_only_for_subject_artifact_producers():
    cat = _catalog()
    assert "bindings" in cat.info("group_analyzer:stacked_weights_pca").outputs
    assert "bindings" not in cat.info("group_analyzer:voxelwise_mean").outputs


def test_utility_nodes_and_policies():
    cat = _catalog()
    bundle = cat.info("utility:bundle_features")
    assert bundle.inputs["features"]["multiple"] and bundle.native
    assert cat.info("analyzer:variance_partition").error_policy == "isolate"
    assert cat.info("model:bootstrap_ridge").error_policy == "fail"
    assert cat.info("qa_reporter:model.score_histogram").inputs["value"]["type"] == "ModelResult"
    assert "feature_name" in cat.info("feature_extractor:english1000").params_schema


ADDON = '''
from fmriflow.modules._decorators import reporter


@reporter("zz_catalog_addon")
class CatalogAddon:
    """An add-on reporter."""
    name = "zz_catalog_addon"

    def report(self, result, context, config):
        return {}
'''


def test_addon_modules_are_labelled(tmp_path, monkeypatch):
    (tmp_path / "zz_catalog_addon.py").write_text(ADDON)
    try:
        discover_user_modules(tmp_path)
        info = _catalog().info("reporter:zz_catalog_addon")
        assert info.source == "addon" and info.description == "An add-on reporter."
        assert _catalog().info("reporter:metrics").source == "builtin"
    finally:
        _reporters.pop("zz_catalog_addon", None)


def test_catalog_serves_structural_validation():
    cat = _catalog()
    g = GraphSpec(
        nodes=[NodeSpec(id="stim", type="stimulus_loader:textgrid"),
               NodeSpec(id="words", type="feature_extractor:numwords")],
        edges=[EdgeSpec(id="e1", source="stim", target="words", source_handle="stimuli", target_handle="stimuli")],
    )
    assert g.validate(cat) == []
    g.edges[0].target_handle = "nope"
    assert any("target handle 'nope'" in e for e in g.validate(cat))
