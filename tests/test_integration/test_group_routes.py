"""HTTP route tests for the Group Runs view (Phase 4 backend)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _make_group_run(group_root: Path, name: str,
                    subjects: list[tuple[str, str]],
                    write_html: bool = False) -> Path:
    """Materialise a fake group_summary.json under group_root/<name>/.

    `subjects` is a list of (subject_id, status) pairs — status drives the
    stage record that gets written.
    """
    rd = group_root / name
    rd.mkdir(parents=True)
    now = datetime.now(timezone.utc).isoformat()
    subject_summaries = []
    for sid, status in subjects:
        subject_summaries.append({
            "experiment": "demo",
            "subject": sid,
            "started_at": now,
            "finished_at": now,
            "total_elapsed_s": 0.5,
            "stages": [
                {"name": "model", "status": status,
                 "elapsed_s": 0.5, "detail": "stub"}
            ],
            "config_snapshot": {"subject": sid},
        })
    data = {
        "group_name": name,
        "subjects": [s for s, _ in subjects],
        "started_at": now,
        "finished_at": now,
        "total_elapsed_s": 1.0,
        "subject_summaries": subject_summaries,
        "group_stages": [
            {"name": "group_collect", "status": "ok",
             "elapsed_s": 0.1, "detail": ""}
        ],
        "config_snapshot": {"group": name},
    }
    (rd / "group_summary.json").write_text(json.dumps(data))
    if write_html:
        (rd / "group_summary.html").write_text("<html>ok</html>")
    return rd


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A TestClient whose $FMRIFLOW_HOME points at a tmpdir.

    We seed two group runs and let the routes scan them via
    ``paths.group_runs_root()``.
    """
    monkeypatch.setenv("FMRIFLOW_HOME", str(tmp_path / "fhome"))
    # Force a fresh import path cache so paths.home() rereads the env.
    group_root = tmp_path / "fhome" / "group_runs"
    group_root.mkdir(parents=True)

    _make_group_run(group_root, "alpha",
                    subjects=[("S1", "ok"), ("S2", "ok")],
                    write_html=True)
    _make_group_run(group_root, "beta",
                    subjects=[("S1", "ok"), ("S2", "failed"), ("S3", "ok")])

    # Don't spin up the full app — it pulls in form-data parsing etc.
    # Just mount the one router we need under /api against a bare FastAPI.
    from fastapi import FastAPI
    from fmriflow.server.routes.group import router as group_router
    app = FastAPI()
    app.include_router(group_router, prefix="/api")
    return TestClient(app)


def test_list_group_runs(client):
    response = client.get("/api/group-runs")
    assert response.status_code == 200
    runs = response.json()
    assert len(runs) == 2
    names = {r["group_name"] for r in runs}
    assert names == {"alpha", "beta"}

    alpha = next(r for r in runs if r["group_name"] == "alpha")
    assert alpha["n_subjects"] == 2
    assert alpha["status_counts"]["ok"] == 2
    assert alpha["status_counts"]["failed"] == 0
    assert alpha["has_html_report"] is True

    beta = next(r for r in runs if r["group_name"] == "beta")
    assert beta["n_subjects"] == 3
    assert beta["status_counts"]["ok"] == 2
    assert beta["status_counts"]["failed"] == 1
    assert beta["has_html_report"] is False


def test_get_group_run_detail(client):
    response = client.get("/api/group-runs/alpha")
    assert response.status_code == 200
    data = response.json()
    assert data["group_name"] == "alpha"
    assert data["subjects"] == ["S1", "S2"]
    assert len(data["subject_summaries"]) == 2
    assert "run_dir" in data
    assert data.get("html_report") == "group_summary.html"


def test_get_group_run_missing(client):
    response = client.get("/api/group-runs/nope")
    assert response.status_code == 404


def test_get_group_run_rejects_path_traversal(client):
    response = client.get("/api/group-runs/..%2Fetc")
    # Path-traversal lookups must not escape group_runs_root.
    assert response.status_code in (400, 404)
