"""Shared graph core: extension hooks, fan-in ports, type checks, dynamic ports, templates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

import pytest

from fmriflow.graph import (
    EdgeSpec,
    GraphSpec,
    NodeSpec,
    TemplateTiers,
    TypeLattice,
    accepts_many,
    normalize_ports,
    port_type,
)


class _Reg:
    """name -> (inputs, outputs) with full port specs."""

    def __init__(self, spec, dynamic=None):
        self._spec = spec
        self._dynamic = dynamic or {}

    def has(self, name):
        return name in self._spec

    def ports(self, name):
        ins, outs = self._spec[name]
        return normalize_ports(ins), normalize_ports(outs)


LATTICE = TypeLattice()
LATTICE.register("FeatureSet")
LATTICE.register("ModelResult")
LATTICE.register("BandedModelResult", parents=["ModelResult"])


class _TypedGraph(GraphSpec):
    def _edge_errors(self, edge, src, dst, src_port, dst_port, registry):
        s, d = port_type(src_port), port_type(dst_port)
        if not LATTICE.compatible(s, d):
            return [f"edge {edge.id}: {s} cannot feed {d}"]
        return []


REG = _Reg({
    "feat": ({}, {"feature": {"type": "FeatureSet"}}),
    "bundle": ({"features": {"type": "FeatureSet", "multiple": True}}, {"out": {"type": "any"}}),
    "banded": ({}, {"result": {"type": "BandedModelResult"}}),
    "report": ({"result": {"type": "ModelResult"}}, {}),
})


def _edge(i, s, sh, t, th):
    return EdgeSpec(id=i, source=s, target=t, source_handle=sh, target_handle=th)


def test_generic_roundtrip_keeps_reactflow_shape():
    g = GraphSpec(name="g", nodes=[NodeSpec(id="a", type="feat", params={"k": 1})],
                  edges=[_edge("e1", "a", "feature", "b", "features")])
    d = g.to_dict()
    assert d["nodes"][0] == {"id": "a", "type": "feat", "kind": "", "data": {"params": {"k": 1}},
                             "position": {"x": 0.0, "y": 0.0}}
    assert d["edges"][0]["sourceHandle"] == "feature"
    assert GraphSpec.from_yaml(g.to_yaml()).to_dict() == d


def test_multiple_port_accepts_several_edges_in_order():
    g = _TypedGraph(nodes=[NodeSpec(id="f1", type="feat"), NodeSpec(id="f2", type="feat"),
                           NodeSpec(id="b", type="bundle")],
                    edges=[_edge("e1", "f1", "feature", "b", "features"),
                           _edge("e2", "f2", "feature", "b", "features")])
    assert g.validate(REG) == []
    assert [e.source for e in g.predecessors("b")] == ["f1", "f2"]


def test_multiple_port_still_rejects_a_literal_next_to_edges():
    g = _TypedGraph(nodes=[NodeSpec(id="f1", type="feat"),
                           NodeSpec(id="b", type="bundle", literal_inputs={"features": []})],
                    edges=[_edge("e1", "f1", "feature", "b", "features")])
    assert any("fed more than once" in e for e in g.validate(REG))


def test_type_lattice_allows_subtype_and_rejects_mismatch():
    ok = _TypedGraph(nodes=[NodeSpec(id="m", type="banded"), NodeSpec(id="r", type="report")],
                     edges=[_edge("e1", "m", "result", "r", "result")])
    assert ok.validate(REG) == []
    bad = _TypedGraph(nodes=[NodeSpec(id="f", type="feat"), NodeSpec(id="r", type="report")],
                      edges=[_edge("e1", "f", "feature", "r", "result")])
    assert any("FeatureSet cannot feed ModelResult" in e for e in bad.validate(REG))
    assert LATTICE.compatible("any", "ModelResult") and LATTICE.compatible("FeatureSet", "any")


def test_registry_node_ports_hook_is_preferred():
    class DynReg(_Reg):
        def node_ports(self, node):
            outs = {name: {"type": "any"} for name in node.params.get("exports", [])}
            return {}, normalize_ports(outs)

    reg = DynReg({"map": ({}, {}), "report": ({"result": {"type": "ModelResult"}}, {})})
    g = GraphSpec(nodes=[NodeSpec(id="m", type="map", params={"exports": ["result"]}),
                         NodeSpec(id="r", type="report")],
                  edges=[_edge("e1", "m", "result", "r", "result")])
    errors = g.validate(reg)
    # report has no node_ports override in DynReg: its declared inputs are {} there
    assert not any("source handle" in e for e in errors)


def test_unknown_type_cycle_and_messages_use_the_noun():
    g = GraphSpec(inputs={}, nodes=[NodeSpec(id="a", type="nope", bindings={"x": "$inputs.missing"})])
    errors = g.validate(REG)
    assert "node a: unknown node type 'nope'" in errors
    assert any("undeclared graph input" in e for e in errors)
    cyc = GraphSpec(nodes=[NodeSpec(id="a", type="feat"), NodeSpec(id="b", type="feat")],
                    edges=[_edge("e1", "a", "x", "b", "y"), _edge("e2", "b", "x", "a", "y")])
    assert "graph has a cycle" in cyc.validate(None)


def test_subclass_hooks_add_data_fields_and_top_level_keys():
    @dataclass
    class BodyNode(NodeSpec):
        body: dict | None = None

        def data_to_dict(self):
            data = super().data_to_dict()
            if self.body is not None:
                data["body"] = dict(self.body)
            return data

        @classmethod
        def data_from_dict(cls, data):
            out = super().data_from_dict(data)
            out["body"] = dict(data["body"]) if isinstance(data.get("body"), dict) else None
            return out

    @dataclass
    class ScopedGraph(GraphSpec):
        scope: str = "subject"
        NODE_CLS: ClassVar[type] = BodyNode
        WRAPPER_KEY: ClassVar[str] = "graph"

        def _extra_to_dict(self):
            return {"scope": self.scope}

        @classmethod
        def _extra_from_dict(cls, data):
            return {"scope": str(data.get("scope") or "subject")}

    g = ScopedGraph(scope="group", nodes=[BodyNode(id="m", type="map", body={"template": "analyze"})])
    d = g.to_dict()
    assert d["scope"] == "group" and d["nodes"][0]["data"]["body"] == {"template": "analyze"}
    again = ScopedGraph.from_yaml("graph:\n" + "".join("  " + line + "\n" for line in g.to_yaml().splitlines()))
    assert again.to_dict() == d and isinstance(again.nodes[0], BodyNode)


def test_port_helpers():
    assert normalize_ports(["a"]) == {"a": {"kind": "any", "required": False}}
    assert port_type({"kind": "nifti"}) == "nifti" and port_type({"type": "X", "kind": "y"}) == "X"
    assert accepts_many({"multiple": True}) and not accepts_many(None)


def test_template_tiers(tmp_path):
    bundled = tmp_path / "bundled"
    user = tmp_path / "user"
    bundled.mkdir()
    user.mkdir()
    GraphSpec(name="base", nodes=[NodeSpec(id="a", type="feat")]).save(bundled / "base.yaml")
    (user / "not_a_graph.yaml").write_text("something: else\n")
    tiers = TemplateTiers(bundled_dir=bundled, user_dir=lambda: user, graph_cls=GraphSpec)

    assert tiers.names() == ["base"]
    g = tiers.load("base")
    g.run_defaults = {"subject": "01"}
    path = tiers.save_user("mine", g)
    assert path == user / "mine.yaml" and tiers.path("mine")[1] == "user"
    assert tiers.load("mine").run_defaults == {}
    assert {r["name"]: r["tier"] for r in tiers.list()} == {"base": "bundled", "mine": "user"}
    with pytest.raises(ValueError):
        tiers.save_user("base", g)
    with pytest.raises(ValueError):
        tiers.delete_user("base")
    assert tiers.delete_user("mine") is True and tiers.delete_user("mine") is False
    with pytest.raises(KeyError):
        tiers.load("missing")
