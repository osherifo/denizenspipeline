"""Built-in pipeline templates validate against the node library."""

from __future__ import annotations

import pytest

from fmriflow.preproc.node_registry import NodeRegistry
from fmriflow.preproc.templates import list_templates, load_template, template_names

EXPECTED = {"fmriprep_full", "fmriprep_anat_only", "fmriprep_func_precomputed_anat"}


def test_expected_templates_exist():
    assert EXPECTED <= set(template_names())


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_template_validates(name):
    reg = NodeRegistry(user_dirs=[]).discover()
    p = load_template(name)
    assert p.validate(reg) == []
    assert p.manifest.get("backend_node")


def test_fmriprep_templates_are_linear_and_bound():
    for name in ("fmriprep_full", "fmriprep_anat_only"):
        p = load_template(name)
        assert p.is_linear() and len(p.nodes) == 1
        assert p.nodes[0].bindings["bids_dir"] == "$inputs.bids_dir"


def test_list_templates_summary():
    rows = {r["name"]: r for r in list_templates()}
    assert rows["fmriprep_full"]["node_types"] == ["fmriprep"]
    assert set(rows) >= EXPECTED
    assert all(rows[n]["tier"] == "bundled" for n in EXPECTED)


def test_unknown_template():
    with pytest.raises(KeyError):
        load_template("nope")


# ── user tier ───────────────────────────────────────────────────────────


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("FMRIFLOW_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def test_save_user_template_drops_run_defaults_and_lists_with_tier(home):
    from fmriflow.preproc.templates import save_user_template, template_path

    p = load_template("fmriprep_anat_only")
    p.run_defaults = {"subject": "01", "bids_dir": "/data/bids"}
    path = save_user_template("my_anat", p)
    assert path == home / "addons" / "pipelines" / "my_anat.yaml"

    reloaded = load_template("my_anat")
    assert reloaded.name == "my_anat" and reloaded.run_defaults == {}
    assert template_path("my_anat")[1] == "user"
    rows = {r["name"]: r for r in list_templates()}
    assert rows["my_anat"]["tier"] == "user" and rows["fmriprep_full"]["tier"] == "bundled"
    assert "my_anat" in template_names()


def test_bundled_names_are_protected(home):
    from fmriflow.preproc.templates import delete_user_template, save_user_template

    p = load_template("fmriprep_anat_only")
    with pytest.raises(ValueError):
        save_user_template("fmriprep_full", p)
    with pytest.raises(ValueError):
        delete_user_template("fmriprep_full")
    with pytest.raises(ValueError):
        save_user_template("bad name!", p)


def test_delete_user_template(home):
    from fmriflow.preproc.templates import delete_user_template, save_user_template

    save_user_template("gone_soon", load_template("fmriprep_anat_only"))
    assert delete_user_template("gone_soon") is True
    assert delete_user_template("gone_soon") is False
    assert "gone_soon" not in template_names()


def test_non_pipeline_files_in_addons_are_ignored(home):
    """Old stack presets share addons/pipelines/; they are not templates."""
    d = home / "addons" / "pipelines"
    d.mkdir(parents=True)
    (d / "old_preset.yaml").write_text("bootstrap: fmriprep\ntransforms: [smooth]\n")
    (d / "broken.yaml").write_text(":: not yaml ::\n- [")
    assert "old_preset" not in template_names()
    assert "broken" not in template_names()


def test_concrete_path_warnings():
    from fmriflow.preproc.templates import concrete_path_warnings

    p = load_template("fmriprep_anat_only")
    assert concrete_path_warnings(p) == []
    p.nodes[0].params["fs_license"] = "/opt/freesurfer/license.txt"
    p.nodes[0].literal_inputs["extra"] = ["a", "~/x"]
    w = concrete_path_warnings(p)
    assert len(w) == 2 and "fmriprep.fs_license" in w[0] and "fmriprep.extra" in w[1]
