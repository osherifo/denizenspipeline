"""HTTP route tests for the Group Runs view."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _summary_payload(name: str, subjects: list[tuple[str, str]],
                     run_id: str = "") -> dict:
    """Build a ``GroupRunSummary``-shaped dict."""
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
        "run_id": run_id,
    }
    return data


def _write_run(group_dir: Path, run_id: str, name: str,
               subjects: list[tuple[str, str]],
               write_html: bool = False, write_log: bool = False) -> Path:
    """New layout: <group_dir>/<run_id>/group_summary.json + optionally log/html."""
    rd = group_dir / run_id
    rd.mkdir(parents=True)
    (rd / "group_summary.json").write_text(
        json.dumps(_summary_payload(name, subjects, run_id=run_id)))
    if write_html:
        (rd / "group_summary.html").write_text("<html>ok</html>")
    if write_log:
        (rd / "group.log").write_text("INFO group log\n")
    return rd


def _write_legacy(group_dir: Path, name: str,
                  subjects: list[tuple[str, str]]) -> Path:
    """Legacy layout: <group_dir>/group_summary.json (no timestamped subdir)."""
    group_dir.mkdir(parents=True, exist_ok=True)
    (group_dir / "group_summary.json").write_text(
        json.dumps(_summary_payload(name, subjects)))
    return group_dir


@pytest.fixture
def client(tmp_path, monkeypatch):
    """TestClient whose $FMRIFLOW_HOME points at a tmpdir.

    Seeds:
    - alpha:  two timestamped runs (20260530T100000Z, 20260530T120000Z)
    - beta:   one timestamped run + a legacy summary
    - gamma:  legacy layout only
    """
    monkeypatch.setenv("FMRIFLOW_HOME", str(tmp_path / "fhome"))
    group_root = tmp_path / "fhome" / "group_runs"
    group_root.mkdir(parents=True)

    _write_run(group_root / "alpha", "20260530T100000Z", "alpha",
               [("S1", "ok"), ("S2", "ok")],
               write_html=True, write_log=True)
    _write_run(group_root / "alpha", "20260530T120000Z", "alpha",
               [("S1", "ok"), ("S2", "ok")])
    _write_run(group_root / "beta", "20260530T130000Z", "beta",
               [("S1", "ok"), ("S2", "failed"), ("S3", "ok")])
    _write_legacy(group_root / "beta", "beta",
                  [("S1", "ok"), ("S2", "warning")])
    _write_legacy(group_root / "gamma", "gamma",
                  [("S1", "ok")])

    from fastapi import FastAPI
    from fmriflow.server.routes.group import router as group_router
    app = FastAPI()
    app.include_router(group_router, prefix="/api")
    return TestClient(app)


def test_list_includes_new_and_legacy_runs(client):
    runs = client.get("/api/group-runs").json()
    # Two for alpha + two for beta (timestamped + legacy) + one for gamma = 5
    assert len(runs) == 5

    names = [r["group_name"] for r in runs]
    assert names.count("alpha") == 2
    assert names.count("beta") == 2
    assert names.count("gamma") == 1

    # New-layout runs carry their run_id; legacy runs have empty run_id.
    alpha_runs = [r for r in runs if r["group_name"] == "alpha"]
    assert sorted(r["run_id"] for r in alpha_runs) == [
        "20260530T100000Z", "20260530T120000Z",
    ]
    gamma = next(r for r in runs if r["group_name"] == "gamma")
    assert gamma["run_id"] == ""


def test_list_advertises_html_and_log(client):
    runs = client.get("/api/group-runs").json()
    a100 = next(r for r in runs
                if r["group_name"] == "alpha"
                and r["run_id"] == "20260530T100000Z")
    assert a100["has_html_report"] is True
    assert a100["has_log"] is True
    a120 = next(r for r in runs
                if r["group_name"] == "alpha"
                and r["run_id"] == "20260530T120000Z")
    assert a120["has_html_report"] is False
    assert a120["has_log"] is False


def test_list_status_counts(client):
    runs = client.get("/api/group-runs").json()
    beta_new = next(r for r in runs
                    if r["group_name"] == "beta"
                    and r["run_id"] == "20260530T130000Z")
    assert beta_new["status_counts"]["ok"] == 2
    assert beta_new["status_counts"]["failed"] == 1


def test_get_new_layout_detail(client):
    r = client.get("/api/group-runs/alpha/20260530T100000Z")
    assert r.status_code == 200
    d = r.json()
    assert d["group_name"] == "alpha"
    assert d.get("html_report") == "group_summary.html"
    assert d.get("group_log") == "group.log"
    assert d["run_id"] == "20260530T100000Z"


def test_get_legacy_layout_detail(client):
    r = client.get("/api/group-runs/gamma")
    assert r.status_code == 200
    d = r.json()
    assert d["group_name"] == "gamma"
    # Legacy summary has no run_id field set.
    assert d.get("run_id", "") == ""


def test_get_missing_run_id_404(client):
    assert client.get("/api/group-runs/alpha/does-not-exist").status_code == 404


def test_get_missing_group_legacy_404(client):
    assert client.get("/api/group-runs/nope").status_code == 404


def test_path_traversal_rejected(client):
    # ".." in either segment must not escape the canonical root.
    assert client.get("/api/group-runs/..%2Fetc").status_code in (400, 404)
    # URL-encoded ".." gets through path-normalisation as a real segment.
    assert client.get("/api/group-runs/alpha/%2E%2E").status_code in (400, 404)
    assert client.get("/api/group-runs/.hidden/x").status_code in (400, 404)
