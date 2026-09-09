"""Built-in pipeline templates validate against the node library."""

from __future__ import annotations

import pytest

from fmriflow.preproc.node_registry import NodeRegistry
from fmriflow.preproc.templates import list_templates, load_template, template_names

EXPECTED = {"fmriprep_full", "fmriprep_anat_only", "fmriprep_func_precomputed_anat",
            "derivatives_smooth_regress", "reference_nipype"}


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
    assert rows["derivatives_smooth_regress"]["node_types"] == ["derivatives_source", "smooth", "regress_confounds"]


def test_unknown_template():
    with pytest.raises(KeyError):
        load_template("nope")
