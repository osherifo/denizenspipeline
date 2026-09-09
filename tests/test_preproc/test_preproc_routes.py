"""HTTP surface: pipelines, templates, nodes, runs."""

from __future__ import annotations

import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

nib = pytest.importorskip("nibabel")
nipype = pytest.importorskip("nipype")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FMRIFLOW_HOME", str(tmp_path / "home"))
    from fmriflow.server.app import create_app
    app = create_app()
    return TestClient(app)


def test_templates_and_nodes(client):
    t = client.get("/api/preproc/pipelines/templates").json()["templates"]
    assert {x["name"] for x in t} >= {"fmriprep_full", "fmriprep_anat_only"}
    p = client.get("/api/preproc/pipelines/templates/fmriprep_anat_only").json()["pipeline"]
    assert p["nodes"][0]["type"] == "fmriprep"
    assert client.get("/api/preproc/pipelines/templates/nope").status_code == 404

    nodes = client.get("/api/preproc/nodes").json()["nodes"]
    names = {n["name"] for n in nodes}
    assert {"fmriprep", "smooth", "bids_source", "reference_fsl_ants", "select"} <= names
    fp = client.get("/api/preproc/nodes/fmriprep").json()
    assert fp["kind"] == "container_app" and "mode" in fp["params_schema"] and fp["source_code"]
    assert fp["ui"]["inner_dag"] and fp["ui"]["report"] == "report_html" and fp["ui"]["label_map"] == "fmriprep"
    assert client.get("/api/preproc/nodes/identity/preflight").json()["ok"]
    assert client.get("/api/preproc/nodes/nope").status_code == 404
    assert "preproc_node" in client.get("/api/preproc/nodes/scaffold/interface").json()["code"]


def test_pipeline_crud_and_validate(client, sample_pipeline):
    p = sample_pipeline("derivatives_smooth_regress").to_dict()
    r = client.put("/api/preproc/pipelines/mine", json={"pipeline": p})
    assert r.status_code == 200 and r.json()["errors"] == []
    listing = client.get("/api/preproc/pipelines").json()
    assert [x["name"] for x in listing["pipelines"]] == ["mine"]
    got = client.get("/api/preproc/pipelines/mine").json()["pipeline"]
    assert got["name"] == "mine" and len(got["nodes"]) == 3

    p["edges"][0]["targetHandle"] = "bogus"
    v = client.post("/api/preproc/pipelines/validate", json={"pipeline": p}).json()
    assert not v["ok"] and any("bogus" in e for e in v["errors"])
    assert client.put("/api/preproc/pipelines/bad name", json={"pipeline": p}).status_code == 400
    assert client.delete("/api/preproc/pipelines/mine").json()["deleted"]
    assert client.get("/api/preproc/pipelines/mine").status_code == 404


def test_save_custom_node_and_rescan(client, tmp_path):
    code = client.get("/api/preproc/nodes/scaffold/interface").json()["code"].replace("my_node", "route_node")
    r = client.post("/api/preproc/nodes", json={"name": "route_node", "code": code})
    assert r.status_code == 200
    assert "route_node" in {n["name"] for n in client.get("/api/preproc/nodes").json()["nodes"]}
    assert client.post("/api/preproc/nodes", json={"name": "x", "code": "def ("}).status_code == 400


def test_run_lifecycle_over_http(client, tmp_path):
    src = tmp_path / "in.nii.gz"
    nib.save(nib.Nifti1Image(np.zeros((2, 2, 2, 3), dtype="float32"), np.eye(4)), src)
    pipeline = {
        "name": "http",
        "nodes": [
            {"id": "ident", "type": "identity", "data": {"literal_inputs": {"in_file": str(src)}}},
            {"id": "sm", "type": "smooth", "data": {"params": {"fwhm": 1.0}}},
        ],
        "edges": [{"id": "e", "source": "ident", "target": "sm", "sourceHandle": "out_file", "targetHandle": "in_file"}],
        "manifest": {"backend_node": "ident", "bold_from": "sm.out_file"},
    }
    r = client.post("/api/preproc/pipelines/run", json={"pipeline": pipeline, "subject": "01", "output_dir": str(tmp_path / "out")})
    assert r.status_code == 200, r.text
    run_id = r.json()["run_id"]

    for _ in range(120):
        s = client.get(f"/api/preproc/runs/{run_id}").json()
        if s["status"] != "running":
            break
        time.sleep(0.5)
    assert s["status"] == "done", s
    assert {n["leaf"] for n in s["nipype_status"]["recent_nodes"]} == {"ident", "sm"}
    assert s["job"]["pipeline"]["name"] == "http"

    ev = client.get(f"/api/preproc/runs/{run_id}/events").json()
    assert ev["events"][0]["event"] == "started" and ev["offset"] > 0
    assert client.get(f"/api/preproc/runs/{run_id}/log").status_code == 200
    assert run_id in {x["run_id"] for x in client.get("/api/preproc/runs").json()["runs"]}

    tree = client.get(f"/api/preproc/runs/{run_id}/work_tree").json()
    assert any(leaf.endswith("sm") for leaf in [l["path"] if isinstance(l, dict) else l for l in tree["leaves"]])

    assert client.post(f"/api/preproc/runs/{run_id}/resume").status_code == 200
    assert client.get("/api/preproc/runs/nope").status_code == 404


def test_run_rejects_bad_pipeline(client, tmp_path):
    r = client.post("/api/preproc/pipelines/run", json={"pipeline": {"nodes": [{"id": "a", "type": "nope"}]}, "subject": "01", "output_dir": str(tmp_path)})
    assert r.status_code == 400
    r = client.post("/api/preproc/pipelines/run", json={"subject": "01", "output_dir": str(tmp_path)})
    assert r.status_code == 400
