"""fmriflow preproc migrate: stack presets, post-preproc graphs and legacy configs -> pipelines."""

from __future__ import annotations

import yaml

from fmriflow.preproc.migrate import (
    legacy_config_to_pipeline,
    migrate_all,
    post_preproc_to_pipeline,
    stack_to_pipeline,
)
from fmriflow.preproc.node_registry import NodeRegistry


def _reg():
    return NodeRegistry(include_parked=True, user_dirs=[]).discover()


def test_stack_preset_becomes_a_linear_pipeline():
    preset = {"name": "fp_smooth", "description": "d", "stack": {
        "bootstrap": {"kind": "fmriprep", "params": {"mode": "anat_only"}},
        "transforms": [{"name": "smooth", "params": {"fwhm": 4}}, {"name": "regress_confounds", "params": {}}],
    }}
    p = stack_to_pipeline(preset, "fp_smooth")
    assert [n.type for n in p.nodes] == ["fmriprep", "smooth", "regress_confounds"]
    assert p.nodes[0].kind == "container_app" and p.nodes[0].bindings["bids_dir"] == "$inputs.bids_dir"
    assert p.nodes[1].iter == {"handle": "in_file"}
    assert p.manifest == {"backend_node": "bootstrap", "bold_from": "regress_confounds.out_file"}
    assert p.is_linear() and p.validate(_reg()) == []


def test_passthrough_preset_becomes_a_derivatives_source():
    p = stack_to_pipeline({"stack": {"bootstrap": {"kind": "passthrough", "params": {}}, "transforms": []}}, "pt")
    assert p.nodes[0].type == "derivatives_source" and "derivatives_dir" in p.inputs
    assert p.validate(_reg()) == []


def test_post_preproc_graph_converts_sources_literals_and_iter():
    wf = {"name": "sm", "inputs": {}, "outputs": {"out_file": {"from": "sm.out_file"}}, "graph": {
        "nodes": [
            {"id": "src", "type": "preproc_run", "data": {"params": {"run_name": "r1"}}, "position": {"x": 0, "y": 0}},
            {"id": "sm", "type": "smooth", "data": {"params": {"fwhm": 3, "_iter": {"handle": "in_file"}, "_inputs": {}}}, "position": {"x": 1, "y": 0}},
        ],
        "edges": [{"id": "e", "source": "src", "target": "sm", "sourceHandle": "out_file", "targetHandle": "in_file"}],
    }}
    p = post_preproc_to_pipeline(wf, "sm")
    assert p.nodes[0].type == "manifest_source" and p.nodes[0].params == {"run_name": "r1"}
    assert p.nodes[1].params == {"fwhm": 3} and p.nodes[1].iter == {"handle": "in_file"}
    assert p.edges[0].source_handle == "bold"
    assert p.manifest == {"backend_node": "src", "bold_from": "sm.out_file"}
    assert p.validate(_reg()) == []


def test_legacy_config_becomes_pipeline_plus_reference():
    section = {"subject": "01", "backend": "fmriprep", "bids_dir": "/b", "output_dir": "/o",
               "work_dir": "/w", "backend_params": {"mode": "anat_only", "container": "img"}}
    p, new_section = legacy_config_to_pipeline(section, "anat")
    assert p.nodes[0].type == "fmriprep" and p.nodes[0].params["mode"] == "anat_only"
    assert new_section == {"pipeline": "anat", "subject": "01", "output_dir": "/o", "bids_dir": "/b", "work_dir": "/w"}
    assert p.validate(_reg()) == []


def test_migrate_all_converts_and_retires_originals(tmp_path):
    presets = tmp_path / "presets"; presets.mkdir()
    (presets / "one.yaml").write_text(yaml.safe_dump({"name": "one", "stack": {"bootstrap": {"kind": "fmriprep", "params": {}}, "transforms": []}}))
    pp = tmp_path / "pp"; pp.mkdir()
    (pp / "two.yaml").write_text(yaml.safe_dump({"name": "two", "graph": {"nodes": [{"id": "s", "type": "smooth", "data": {"params": {}}}], "edges": []}}))
    cfg = tmp_path / "configs"; cfg.mkdir()
    (cfg / "legacy.yaml").write_text(yaml.safe_dump({"preproc": {"subject": "01", "backend": "fmriprep", "output_dir": "/o", "backend_params": {}}}))
    wfs = tmp_path / "workflows"; wfs.mkdir()
    (wfs / "w.yaml").write_text(yaml.safe_dump({"workflow": {"name": "w"}, "preproc": {"subject": "01", "backend": "custom", "output_dir": "/o", "backend_params": {"command": "x"}}}))

    report = migrate_all(presets_dir=presets, post_preproc_dir=pp, configs_dir=cfg, workflow_dirs=[wfs], dry_run=True)
    assert len(report.converted) == 4 and not (cfg / "one.yaml").exists()

    report = migrate_all(presets_dir=presets, post_preproc_dir=pp, configs_dir=cfg, workflow_dirs=[wfs])
    assert len(report.converted) == 4, report.summary()
    assert (cfg / "one.yaml").exists() and (presets / "one.yaml.migrated").exists()
    assert (cfg / "two.yaml").exists()
    legacy = yaml.safe_load((cfg / "legacy.yaml").read_text())["preproc"]
    assert legacy["pipeline"] == "legacy_pipeline" and (cfg / "legacy_pipeline.yaml").exists()
    w = yaml.safe_load((wfs / "w.yaml").read_text())
    assert w["preproc"]["pipeline"] == "w_pipeline" and w["workflow"]["name"] == "w"
    # Second pass is a no-op.
    again = migrate_all(presets_dir=presets, post_preproc_dir=pp, configs_dir=cfg, workflow_dirs=[wfs])
    assert again.converted == []
