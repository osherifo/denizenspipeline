"""Directory browsing is restricted to the server's data roots."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / "data" / "dicoms" / "sub01" / "ses1").mkdir(parents=True)
    (home / "data" / "dicoms" / "sub01" / "a.dcm").write_bytes(b"x" * 10)
    (home / "data" / "dicoms" / ".hidden").mkdir()
    (home / "data" / "bids").mkdir()
    extra = tmp_path / "share"
    (extra / "study").mkdir(parents=True)
    monkeypatch.setenv("FMRIFLOW_HOME", str(home))
    monkeypatch.setenv("FMRIFLOW_BROWSE_ROOTS", str(extra))
    from fmriflow.server.app import create_app
    return TestClient(create_app()), home, extra


def test_roots_and_listing(client):
    c, home, extra = client
    roots = c.get("/api/fs/roots").json()["roots"]
    labels = [r["label"] for r in roots]
    assert labels[:2] == ["dicoms", "bids"] and "data" in labels and "home" in labels
    assert any(r["path"] == str(extra.resolve()) and r["kind"] == "extra" for r in roots)

    r = c.get("/api/fs/list", params={"path": str(home / "data" / "dicoms" / "sub01")}).json()
    assert [e["name"] for e in r["entries"]] == ["ses1", "a.dcm"]
    assert r["entries"][0]["is_dir"] and r["entries"][1]["size"] == 10
    assert r["parent"] == str((home / "data" / "dicoms").resolve())
    r2 = c.get("/api/fs/list", params={"path": str(home / "data" / "dicoms"), "show_files": "false"}).json()
    assert [e["name"] for e in r2["entries"]] == ["sub01"]          # hidden dirs skipped


def test_outside_roots_is_refused(client):
    c, home, extra = client
    assert c.get("/api/fs/list", params={"path": "/"}).status_code == 403
    assert c.get("/api/fs/list", params={"path": str(home / "data" / "../../..")}).status_code == 403
    assert c.get("/api/fs/list", params={"path": str(extra / "study")}).status_code == 200
    assert c.get("/api/fs/list", params={"path": str(home / "data" / "nope")}).status_code == 404


def test_exists_reports_the_servers_view(client):
    c, home, _ = client
    assert c.get("/api/fs/exists", params={"path": str(home / "data" / "bids")}).json()["is_dir"]
    assert c.get("/api/fs/exists", params={"path": "/mnt/definitely/not/here"}).json()["exists"] is False
