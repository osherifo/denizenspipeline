"""Unified node registry: tiers, shadowing, aliases, ports."""

from __future__ import annotations

import textwrap
import pytest

from fmriflow.preproc import node_registry as nr
from fmriflow.preproc.node_registry import NodeRegistry, normalize_ports, preproc_node


BUILTINS = {
    "identity", "smooth", "mask_apply", "regress_confounds",
    "bids_source", "manifest_source", "derivatives_source",
}


def test_builtins_are_discovered_with_kinds_and_sources():
    reg = NodeRegistry(user_dirs=[]).discover()
    assert BUILTINS <= set(reg.names())
    assert reg.kind("smooth") == "interface"
    assert reg.kind("bids_source") == "source"
    assert reg.source("smooth") == "built-in"
    info = reg.info("smooth")
    assert info.name == "smooth" and info.version and "fwhm" in info.params_schema
    assert set(info.inputs) == {"in_file"} and set(info.outputs) == {"out_file"}


def test_normalize_ports_accepts_lists_and_dicts():
    assert normalize_ports(["a", "b"]) == {
        "a": {"kind": "file", "required": False},
        "b": {"kind": "file", "required": False},
    }
    assert normalize_ports({"x": {"kind": "dir", "required": True}}) == {
        "x": {"kind": "dir", "required": True}
    }
    assert normalize_ports(None) == {}


def test_user_dir_node_is_discovered_and_shadows_builtin(tmp_path):
    (tmp_path / "my_smooth.py").write_text(textwrap.dedent('''
        from fmriflow.preproc.node_registry import preproc_node

        @preproc_node("smooth")
        class MySmooth:
            version = "9.9"
            INPUTS = ["in_file"]
            OUTPUTS = ["out_file"]
            def run(self, inputs, out_dir, params):
                return {"out_file": inputs["in_file"]}

        @preproc_node("brand_new", kind="source")
        class BrandNew:
            OUTPUTS = ["bold"]
            def run(self, inputs, out_dir, params):
                return {}
    '''))
    reg = NodeRegistry(user_dirs=[tmp_path]).discover()
    assert reg.source("smooth") == "user"
    assert reg.info("smooth").version == "9.9"
    assert ("smooth", "built-in") in reg.shadowed()
    assert reg.kind("brand_new") == "source"
    # Restore the built-in for later tests in this process.
    from fmriflow.preproc.nodes.smooth import SmoothNode
    preproc_node("smooth")(SmoothNode)


def test_old_workflow_decorator_registers_a_composite(tmp_path):
    """An addon written against the old workflow contract keeps working."""
    (tmp_path / "legacy_wf.py").write_text(textwrap.dedent('''
        from fmriflow.preproc.workflow_registry import register_preproc_workflow

        @register_preproc_workflow("legacy_clean")
        class LegacyClean:
            name = "legacy_clean"
            version = "0.1"
            description = "old-style"
            PARAM_SCHEMA = {}
            REQUIRED_PYTHON = []; REQUIRED_TOOLS = []; REQUIRED_ENV = []
            CONTAINER = None
            def validate(self, config): return []
            def build(self, config): return None
            def to_manifest(self, config, outputs): return None
    '''))
    reg = NodeRegistry(user_dirs=[tmp_path]).discover()
    assert reg.kind("legacy_clean") == "composite"
    assert reg.source("legacy_clean") == "user"


def test_old_transform_and_nipype_node_decorators_register_interfaces():
    from fmriflow.preproc.transform_registry import register_transform
    from fmriflow.modules._decorators import nipype_node

    with pytest.warns(DeprecationWarning):
        @register_transform("_t_alias")
        class T:
            INPUTS = ["in_file"]; OUTPUTS = ["out_file"]
            def run(self, i, o, p): return {}

    with pytest.warns(DeprecationWarning):
        @nipype_node("_n_alias")
        class N:
            INPUTS = ["in_file"]; OUTPUTS = ["out_file"]
            def run(self, i, o, p): return {}

    table = nr.registered_nodes()
    assert table["_t_alias"] is T and T.NODE_KIND == "interface"
    assert table["_n_alias"] is N and N.NODE_KIND == "interface"


def test_container_apps_come_from_the_nodes_package():
    reg = NodeRegistry(user_dirs=[]).discover()
    for name in ("fmriprep", "custom_shell", "bids_app"):
        assert reg.cls(name).__module__.startswith("fmriflow.preproc.nodes")


def test_unknown_kind_is_rejected():
    with pytest.raises(ValueError):
        preproc_node("x", kind="banana")


def test_same_file_loaded_twice_is_not_a_shadow(tmp_path, caplog):
    (tmp_path / "dup.py").write_text(textwrap.dedent('''
        from fmriflow.preproc.node_registry import preproc_node
        @preproc_node("dup_node")
        class Dup:
            OUTPUTS = ["out_file"]
            def run(self, i, o, p): return {}
    '''))
    NodeRegistry(user_dirs=[tmp_path]).discover()
    with caplog.at_level("WARNING"):
        reg = NodeRegistry(user_dirs=[tmp_path]).discover()
    assert "Re-registering" not in caplog.text
    assert ("dup_node", "user") not in reg.shadowed()


def test_preflight_runs_on_class_requirements():
    reg = NodeRegistry(user_dirs=[]).discover()
    assert reg.preflight("identity").ok
