"""copy_heuristic + POST /api/convert/heuristics/{name}/copy."""

from __future__ import annotations

import yaml
from fastapi.testclient import TestClient


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("FMRIFLOW_HOME", str(tmp_path / "home"))
    from fmriflow.server.app import create_app
    return TestClient(create_app(derivatives_dir=str(tmp_path / "derivatives")))


def test_copy_duplicates_code_and_sidecar_with_new_name(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    c.post("/api/convert/heuristics/save", json={
        "name": "orig", "code": "# original\n", "description": "d", "version": "1.0", "tasks": ["story"],
    })
    r = c.post("/api/convert/heuristics/orig/copy", json={"new_name": "orig_v2"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "orig_v2" and body["source"] == "orig"
    assert c.get("/api/convert/heuristics/orig_v2/code").json()["code"] == "# original\n"
    sidecar = yaml.safe_load(open(body["path"].replace(".py", ".yaml")))
    assert sidecar["name"] == "orig_v2"
    assert sidecar["description"] == "d" and sidecar["version"] == "1.0" and sidecar["tasks"] == ["story"]
    # the original is untouched
    assert c.get("/api/convert/heuristics/orig/code").json()["code"] == "# original\n"


def test_copy_of_bundled_heuristic_lands_in_user_tier(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    names = [h["name"] for h in c.get("/api/convert/heuristics").json()["heuristics"]]
    assert names, "expected bundled heuristics"
    r = c.post(f"/api/convert/heuristics/{names[0]}/copy", json={"new_name": "mine"})
    assert r.status_code == 200, r.text
    assert str(tmp_path / "home") in r.json()["path"]


def test_copy_refuses_existing_target_and_bad_names(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    c.post("/api/convert/heuristics/save", json={"name": "a", "code": "# a\n"})
    c.post("/api/convert/heuristics/save", json={"name": "b", "code": "# b\n"})
    assert c.post("/api/convert/heuristics/a/copy", json={"new_name": "b"}).status_code == 409
    assert c.post("/api/convert/heuristics/a/copy", json={"new_name": "../x"}).status_code == 400
    assert c.post("/api/convert/heuristics/nope/copy", json={"new_name": "c"}).status_code == 404
