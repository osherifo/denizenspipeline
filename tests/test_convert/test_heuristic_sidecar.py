"""Sidecar metadata written through /api/convert/heuristics/save."""

from __future__ import annotations

import yaml
from fastapi.testclient import TestClient


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("FMRIFLOW_HOME", str(tmp_path / "home"))
    from fmriflow.server.app import create_app
    return TestClient(create_app(derivatives_dir=str(tmp_path / "derivatives")))


def test_save_writes_sidecar_and_listing_reflects_it(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    r = c.post("/api/convert/heuristics/save", json={
        "name": "my_study", "code": "def infotodict(seqinfo):\n    return {}\n",
        "description": "Story listening", "version": "1.2",
        "tasks": ["story", " rest ", ""], "notes": "first cut",
    })
    assert r.status_code == 200, r.text
    path = r.json()["path"]
    sidecar = yaml.safe_load(open(path.replace(".py", ".yaml")))
    assert sidecar["description"] == "Story listening"
    assert sidecar["version"] == "1.2"
    assert sidecar["tasks"] == ["story", "rest"]
    assert sidecar["notes"] == "first cut"

    listing = {h["name"]: h for h in c.get("/api/convert/heuristics").json()["heuristics"]}
    assert listing["my_study"]["version"] == "1.2"
    assert listing["my_study"]["notes"] == "first cut"


def test_save_without_metadata_keeps_existing_sidecar(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    c.post("/api/convert/heuristics/save", json={
        "name": "my_study", "code": "# v1\n", "description": "keep me", "version": "1",
    })
    r = c.post("/api/convert/heuristics/save", json={"name": "my_study", "code": "# v2\n"})
    assert r.status_code == 200
    listing = {h["name"]: h for h in c.get("/api/convert/heuristics").json()["heuristics"]}
    assert listing["my_study"]["description"] == "keep me"
    assert listing["my_study"]["version"] == "1"


def test_empty_string_clears_a_field(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    c.post("/api/convert/heuristics/save", json={
        "name": "my_study", "code": "# v1\n", "description": "old", "version": "1",
    })
    c.post("/api/convert/heuristics/save", json={
        "name": "my_study", "code": "# v1\n", "description": "",
    })
    listing = {h["name"]: h for h in c.get("/api/convert/heuristics").json()["heuristics"]}
    assert listing["my_study"]["description"] is None
    assert listing["my_study"]["version"] == "1"
