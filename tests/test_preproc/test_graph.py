"""Pipeline graph model: round-trip, topology, validation."""

from __future__ import annotations

import pytest

from fmriflow.preproc.graph import (
    Pipeline,
    PipelineEdge,
    PipelineNode,
    PipelineRunRequest,
)


class _FakeRegistry:
    """Minimal registry double: name -> (kind, inputs, outputs)."""

    def __init__(self, spec):
        self._spec = spec

    def has(self, name):
        return name in self._spec

    def kind(self, name):
        return self._spec[name][0]

    def ports(self, name):
        kind, ins, outs = self._spec[name]
        mk = lambda ps: {p: {"kind": "file", "required": False} for p in ps}
        return mk(ins), mk(outs)


REG = _FakeRegistry({
    "src": ("source", [], ["bold"]),
    "smooth": ("interface", ["in_file"], ["out_file"]),
    "mask_apply": ("interface", ["in_file", "mask_file"], ["out_file"]),
})


def _chain():
    return Pipeline(
        name="chain",
        inputs={"bids_dir": {"kind": "dir"}},
        nodes=[
            PipelineNode(id="a", type="src", kind="source", bindings={"bids_dir": "$inputs.bids_dir"}),
            PipelineNode(id="b", type="smooth", params={"fwhm": 4.0}),
            PipelineNode(id="c", type="mask_apply"),
        ],
        edges=[
            PipelineEdge(id="e1", source="a", target="b", source_handle="bold", target_handle="in_file"),
            PipelineEdge(id="e2", source="b", target="c", source_handle="out_file", target_handle="in_file"),
        ],
        manifest={"backend_node": "a", "bold_from": "c.out_file"},
    )


def test_roundtrip_dict_and_yaml():
    p = _chain()
    again = Pipeline.from_dict(p.to_dict())
    assert again.to_dict() == p.to_dict()
    assert Pipeline.from_yaml(p.to_yaml()).to_dict() == p.to_dict()


def test_reactflow_shape_is_preserved():
    d = _chain().to_dict()
    node = d["nodes"][1]
    assert set(node) >= {"id", "type", "kind", "data", "position"}
    assert node["data"]["params"] == {"fwhm": 4.0}
    edge = d["edges"][0]
    assert edge["sourceHandle"] == "bold" and edge["targetHandle"] == "in_file"


def test_from_yaml_accepts_pipeline_wrapper():
    text = "pipeline:\n  name: w\n  nodes:\n    - id: a\n      type: src\n  edges: []\n"
    assert Pipeline.from_yaml(text).name == "w"


def test_newer_schema_is_rejected():
    with pytest.raises(ValueError):
        Pipeline.from_dict({"schema_version": 99, "nodes": []})


def test_topo_order_and_linear():
    p = _chain()
    assert [n.id for n in p.topo_order()] == ["a", "b", "c"]
    assert p.is_linear()
    p.edges.append(PipelineEdge(id="e3", source="a", target="c", source_handle="bold", target_handle="mask_file"))
    assert not p.is_linear()
    assert [n.id for n in p.topo_order()] == ["a", "b", "c"]


def test_cycle_is_detected():
    p = _chain()
    p.edges.append(PipelineEdge(id="back", source="c", target="a", source_handle="out_file", target_handle="x"))
    with pytest.raises(ValueError):
        p.topo_order()
    assert any("cycle" in e for e in p.validate())


def test_descendants():
    p = _chain()
    assert p.descendants(["b"]) == {"b", "c"}
    assert p.descendants(["c"]) == {"c"}


def test_validate_clean_graph():
    assert _chain().validate(REG) == []


def test_validate_reports_bad_ports_kinds_and_bindings():
    p = _chain()
    p.nodes[1].kind = "composite"                      # library says interface
    p.edges[1].target_handle = "nope"                  # not in mask_apply.INPUTS
    p.nodes[0].bindings["bids_dir"] = "$inputs.missing"
    p.manifest["backend_node"] = "zzz"
    errors = p.validate(REG)
    assert any("does not match" in e for e in errors)
    assert any("target handle 'nope'" in e for e in errors)
    assert any("undeclared pipeline input" in e for e in errors)
    assert any("backend_node" in e for e in errors)


def test_validate_flags_double_fed_port_and_bad_iter():
    p = _chain()
    p.nodes[1].literal_inputs["in_file"] = "/x.nii"   # also fed by e1
    p.nodes[2].iter = {"handle": "nope", "values": []}
    errors = p.validate(REG)
    assert any("fed more than once" in e for e in errors)
    assert any("iter handle" in e for e in errors)


def test_run_request_roundtrip_and_resolve():
    req = PipelineRunRequest(subject="01", output_dir="/out", bids_dir="/bids", inputs={"extra": 3})
    again = PipelineRunRequest.from_dict(req.to_dict())
    assert again == req
    assert req.resolve_input("subject") == "01"
    assert req.resolve_input("extra") == 3
    with pytest.raises(KeyError):
        req.resolve_input("nope")


def test_run_defaults_roundtrip_and_empty_values_dropped():
    from fmriflow.preproc.graph import Pipeline
    p = Pipeline.from_dict({"name": "x", "run_defaults": {"subject": "01", "bids_dir": "/b", "work_dir": "", "n_procs": None, "plugin": "Linear"}})
    assert p.run_defaults == {"subject": "01", "bids_dir": "/b", "plugin": "Linear"}
    again = Pipeline.from_yaml(p.to_yaml())
    assert again.run_defaults == p.run_defaults
    assert "run_defaults" not in Pipeline(name="t").to_dict()   # templates stay clean


def test_validate_accepts_a_list_literal_on_an_iterated_handle():
    from fmriflow.preproc.graph import Pipeline
    base = {
        "schema_version": 1, "name": "t", "inputs": {},
        "nodes": [{"id": "n", "type": "smooth", "kind": "interface", "position": {"x": 0, "y": 0},
                   "data": {"params": {}, "literal_inputs": {"in_file": ["/a.nii", "/b.nii"]}, "iter": {"handle": "in_file"}}}],
        "edges": [], "manifest": {},
    }
    assert not [e for e in Pipeline.from_dict(base).validate(None) if "iter" in e]
    base["nodes"][0]["data"]["literal_inputs"]["in_file"] = "/a.nii"
    errors = Pipeline.from_dict(base).validate(None)
    assert any("not a list" in e for e in errors)
    del base["nodes"][0]["data"]["literal_inputs"]["in_file"]
    errors = Pipeline.from_dict(base).validate(None)
    assert any("needs an incoming edge, a list literal or 'values'" in e for e in errors)

