"""Integration tests for the Artifact Hub HTTP routes.

Exercises the public ``/api/hub/*`` surface end-to-end. The sources list and
tokens normally persist to ``~/.config/fmriflow/settings.json``; the fixture
redirects that file (and ``$FMRIFLOW_HOME``) into a tmp dir so tests never touch
the developer's real settings or OS keyring, and never hit the network (the
one git flow uses a local ``file://`` bare repo).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fmriflow.core import paths


@pytest.fixture
def client(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("FMRIFLOW_HOME", str(home))
    monkeypatch.delenv("FMRIFLOW_HUB_SOURCES", raising=False)
    # Redirect the persisted settings file so add/remove-source and tokens
    # don't touch the real ~/.config/fmriflow/settings.json.
    monkeypatch.setattr(paths, "RUNTIME_CONFIG_PATH", tmp_path / "settings.json")

    from fmriflow.server.app import create_app
    return TestClient(create_app())


def test_sources_snapshot_shape(client):
    r = client.get("/api/hub/sources")
    assert r.status_code == 200
    body = r.json()
    assert body["sources"] == []
    assert body["env_override"] is False
    assert isinstance(body["preflight"], list)
    assert isinstance(body["keyring_available"], bool)


def test_local_artifacts_lists_user_tier_only(client):
    app = client.app
    app.state.config_store.save_config(
        "hub_test_cfg.yaml", "experiment: e\nsubject: s\n")

    r = client.get("/api/hub/local")
    assert r.status_code == 200
    arts = r.json()["artifacts"]
    assert "hub_test_cfg.yaml" in arts.get("analysis_config", [])
    # A fresh $FMRIFLOW_HOME has no *user* modules — builtin modules must not be
    # offered as publishable (they have no user-tier file to push).
    assert "module" not in arts

    # A stray, unregistered .py in the user modules dir must NOT be offered:
    # it has no known category, so publishing it would break the store schema.
    from fmriflow.server.services.module_loader import get_modules_dir
    mdir = get_modules_dir()
    mdir.mkdir(parents=True, exist_ok=True)
    (mdir / "not_a_real_module.py").write_text("x = 1\n")
    arts2 = client.get("/api/hub/local").json()["artifacts"]
    assert "not_a_real_module" not in arts2.get("module", [])


def test_add_and_remove_source_roundtrip(client):
    r = client.post("/api/hub/sources", json={
        "name": "Demo", "url": "file:///tmp/does-not-need-to-exist.git",
        "tier": "lab", "branch": "main"})
    assert r.status_code == 200
    sources = r.json()["sources"]
    assert len(sources) == 1
    sid = sources[0]["id"]
    assert sources[0]["name"] == "Demo" and sources[0]["branch"] == "main"
    assert sources[0]["token_storage"] == "none"

    r = client.delete(f"/api/hub/sources/{sid}")
    assert r.status_code == 200
    assert r.json()["sources"] == []


def test_install_unknown_source_404(client):
    r = client.post("/api/hub/install", json={
        "source_id": "nope", "kind": "error", "name": "x"})
    assert r.status_code == 404


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_sync_publish_catalog_offline(client, tmp_path):
    app = client.app

    def git(*args, cwd=None):
        p = subprocess.run(["git", *args], cwd=cwd and str(cwd),
                           capture_output=True, text=True)
        assert p.returncode == 0, p.stderr

    bare = tmp_path / "store.git"
    bare.mkdir()
    git("init", "--bare", "-b", "main", str(bare))

    # Register the empty store and sync it — must succeed with an empty catalog.
    r = client.post("/api/hub/sources", json={
        "name": "Store", "url": str(bare), "tier": "lab", "branch": "main"})
    sid = r.json()["sources"][0]["id"]
    r = client.post(f"/api/hub/sources/{sid}/sync")
    assert r.status_code == 200, r.text
    assert r.json()["artifacts"] == 0
    assert client.get("/api/hub/catalog").json()["items"] == []

    # Publish a local config — initialises the empty repo on main.
    app.state.config_store.save_config("pub_cfg.yaml", "experiment: e\nsubject: s\n")
    r = client.post("/api/hub/publish", json={
        "source_id": sid, "kind": "analysis_config", "name": "pub_cfg.yaml"})
    assert r.status_code == 200, r.text
    assert r.json()["pushed"] is True and r.json()["initialized"] is True

    # Re-sync — the catalog now lists it, and validation is clean.
    client.post(f"/api/hub/sources/{sid}/sync")
    items = client.get("/api/hub/catalog").json()["items"]
    assert any(i["name"] == "pub_cfg.yaml" for i in items)
    assert client.get(f"/api/hub/sources/{sid}/validate").json()["problems"] == []
