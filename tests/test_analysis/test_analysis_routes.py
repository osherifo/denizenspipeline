"""Read-only HTTP surface of the analysis node catalog."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FMRIFLOW_HOME", str(tmp_path / "home"))
    from fmriflow.server.app import create_app
    return TestClient(create_app())


def test_nodes_and_port_types(client):
    nodes = client.get("/api/analysis/nodes").json()["nodes"]
    types = {n["type"] for n in nodes}
    assert {"stimulus_loader:textgrid", "model:bootstrap_ridge", "reporter:flatmap",
            "utility:bundle_features"} <= types
    assert "feature_source:compute" not in types
    hidden = client.get("/api/analysis/nodes", params={"include_hidden": True}).json()["nodes"]
    assert "feature_source:compute" in {n["type"] for n in hidden}

    info = client.get("/api/analysis/nodes/qa_reporter:model.score_histogram").json()
    assert info["inputs"]["value"]["type"] == "ModelResult"
    assert client.get("/api/analysis/nodes/model:nope").status_code == 404

    port_types = {t["name"] for t in client.get("/api/analysis/port-types").json()["types"]}
    assert {"ModelResult", "Context", "GroupRun", "any"} <= port_types
