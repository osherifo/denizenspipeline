"""ReactFlow JSON ↔ PostPreprocGraph round-trip + topology + validation."""

from __future__ import annotations

import pytest

from fmriflow.post_preproc.graph import PostPreprocGraph


REACTFLOW = {
    "nodes": [
        {"id": "src", "type": "preproc_run",
         "data": {"params": {"run_name": "task01"}},
         "position": {"x": 0, "y": 0}},
        {"id": "smo", "type": "smooth",
         "data": {"params": {"fwhm": 5.0}},
         "position": {"x": 200, "y": 0}},
        {"id": "msk", "type": "mask_apply",
         "data": {"params": {"mask_path": "/m.nii.gz"}},
         "position": {"x": 400, "y": 0}},
    ],
    "edges": [
        {"id": "e1", "source": "src", "target": "smo",
         "sourceHandle": "out_file", "targetHandle": "in_file"},
        {"id": "e2", "source": "smo", "target": "msk",
         "sourceHandle": "out_file", "targetHandle": "in_file"},
    ],
}


def test_roundtrip_preserves_shape():
    g = PostPreprocGraph.from_reactflow(REACTFLOW)
    out = g.to_reactflow()
    assert {n["id"] for n in out["nodes"]} == {"src", "smo", "msk"}
    assert {e["id"] for e in out["edges"]} == {"e1", "e2"}


def test_topo_order_linear():
    g = PostPreprocGraph.from_reactflow(REACTFLOW)
    order = [n.id for n in g.topo_order()]
    assert order == ["src", "smo", "msk"]


def test_cycle_rejected():
    cyclic = {
        "nodes": [
            {"id": "a", "type": "smooth", "data": {"params": {}}, "position": {}},
            {"id": "b", "type": "smooth", "data": {"params": {}}, "position": {}},
        ],
        "edges": [
            {"id": "e1", "source": "a", "target": "b",
             "sourceHandle": "out_file", "targetHandle": "in_file"},
            {"id": "e2", "source": "b", "target": "a",
             "sourceHandle": "out_file", "targetHandle": "in_file"},
        ],
    }
    g = PostPreprocGraph.from_reactflow(cyclic)
    with pytest.raises(ValueError):
        g.topo_order()


def test_validate_unknown_node_type():
    bad = {
        "nodes": [
            {"id": "x", "type": "no_such_node", "data": {"params": {}},
             "position": {}},
        ],
        "edges": [],
    }
    g = PostPreprocGraph.from_reactflow(bad)
    errors = g.validate_against({"smooth": object})
    assert any("Unknown node type" in e for e in errors)


def test_validate_unknown_handle():
    from fmriflow.modules.nipype_nodes.smooth import SmoothNode

    bogus = {
        "nodes": [
            {"id": "a", "type": "smooth", "data": {"params": {}}, "position": {}},
            {"id": "b", "type": "smooth", "data": {"params": {}}, "position": {}},
        ],
        "edges": [
            {"id": "e1", "source": "a", "target": "b",
             "sourceHandle": "out_file", "targetHandle": "bogus_handle"},
        ],
    }
    g = PostPreprocGraph.from_reactflow(bogus)
    errors = g.validate_against({"smooth": SmoothNode})
    assert any("bogus_handle" in e for e in errors)
