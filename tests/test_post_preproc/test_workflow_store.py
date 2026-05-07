"""Round-trip the post-preproc workflow YAML store."""

from __future__ import annotations

import pytest

from fmriflow.server.services.post_preproc_workflow_store import (
    PostPreprocWorkflowStore,
)


def test_save_get_list_delete(tmp_path):
    store = PostPreprocWorkflowStore(tmp_path)
    graph = {
        "nodes": [{"id": "smo", "type": "smooth", "data": {"params": {}}, "position": {}}],
        "edges": [],
    }
    store.save(
        "smooth_only",
        graph,
        description="just smooth",
        inputs={"in_file": {"from": "smo.in_file"}},
        outputs={"out_file": {"from": "smo.out_file"}},
    )

    listed = store.list()
    assert any(w["name"] == "smooth_only" and w["n_nodes"] == 1 for w in listed)

    got = store.get("smooth_only")
    assert got is not None
    assert got["description"] == "just smooth"
    assert "in_file" in got["inputs"]
    assert "out_file" in got["outputs"]

    assert store.delete("smooth_only") is True
    assert store.get("smooth_only") is None


def test_unsafe_name_rejected(tmp_path):
    store = PostPreprocWorkflowStore(tmp_path)
    with pytest.raises(ValueError):
        store.save("../bad", {"nodes": [], "edges": []})
