"""/api/preproc/runs/{id}/node/{path}/(files|file|pickle) endpoints."""

from __future__ import annotations

import gzip
import json
import pickle
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fmriflow.server.services.preproc_manager import (
    PreprocManager,
    PreprocRunHandle,
)
from fmriflow.server.services.run_registry import RunRegistry, RunStateFile


# ── fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def app_with_run(tmp_path, monkeypatch):
    """An app whose preproc_manager has a single completed run with a
    real on-disk work_dir + a couple of node leaves prepared for us."""
    from fmriflow.server.app import create_app

    work_dir = tmp_path / "work"
    output_dir = tmp_path / "out"
    leaf = work_dir / "fmriprep_wf" / "anat_wf" / "smooth"
    leaf.mkdir(parents=True)
    (leaf / "command.txt").write_text("smooth -fwhm 5\n")
    (leaf / "_inputs.json").write_text(json.dumps({"fwhm": 5.0}))
    (leaf / "ignore.unknown").write_text("not whitelisted")

    # A pickled dict as result_smooth.pklz (gzip-wrapped, like nipype).
    p = leaf / "result_smooth.pklz"
    with gzip.open(p, "wb") as f:
        pickle.dump({"out_file": "/tmp/x.nii.gz", "n_iter": 3}, f)

    # A bogus pickle that won't decode.
    bad = leaf / "broken.pkl"
    bad.write_bytes(b"not actually a pickle")

    app = create_app(derivatives_dir=str(tmp_path / "derivatives"))
    mgr: PreprocManager = app.state.preproc_manager
    handle = PreprocRunHandle(
        run_id="run_demo",
        subject="01",
        backend="fmriprep",
        status="done",
        params={"work_dir": str(work_dir), "output_dir": str(output_dir)},
    )
    mgr.active_runs["run_demo"] = handle
    return app, handle


def test_files_lists_whitelisted_artefacts(app_with_run):
    app, _ = app_with_run
    c = TestClient(app)
    r = c.get(
        "/api/preproc/runs/run_demo/node/fmriprep_wf.anat_wf.smooth/files",
    )
    assert r.status_code == 200
    data = r.json()
    assert data["exists"] is True
    names = {f["name"] for f in data["files"]}
    assert names == {"command.txt", "_inputs.json", "result_smooth.pklz",
                     "broken.pkl"}
    assert "ignore.unknown" not in names

    by_name = {f["name"]: f for f in data["files"]}
    assert by_name["command.txt"]["kind"] == "view"
    assert by_name["_inputs.json"]["kind"] == "view"
    assert by_name["result_smooth.pklz"]["kind"] == "pickle"
    assert by_name["broken.pkl"]["kind"] == "pickle"


def test_files_returns_exists_false_for_missing_leaf(app_with_run):
    app, _ = app_with_run
    c = TestClient(app)
    r = c.get(
        "/api/preproc/runs/run_demo/node/fmriprep_wf.anat_wf.no_such_node/files",
    )
    assert r.status_code == 200
    body = r.json()
    assert body["exists"] is False
    assert body["files"] == []


def test_file_serves_content(app_with_run):
    app, _ = app_with_run
    c = TestClient(app)
    r = c.get(
        "/api/preproc/runs/run_demo/node/fmriprep_wf.anat_wf.smooth/file",
        params={"rel": "command.txt"},
    )
    assert r.status_code == 200
    assert "smooth -fwhm 5" in r.text


def test_file_refuses_unknown_suffix(app_with_run):
    app, _ = app_with_run
    c = TestClient(app)
    r = c.get(
        "/api/preproc/runs/run_demo/node/fmriprep_wf.anat_wf.smooth/file",
        params={"rel": "ignore.unknown"},
    )
    assert r.status_code == 403


def test_file_refuses_path_traversal(app_with_run):
    app, _ = app_with_run
    c = TestClient(app)
    r = c.get(
        "/api/preproc/runs/run_demo/node/fmriprep_wf.anat_wf.smooth/file",
        params={"rel": "../../../etc/passwd.txt"},
    )
    assert r.status_code in (403, 404)


def test_pickle_decodes_dict(app_with_run):
    app, _ = app_with_run
    c = TestClient(app)
    r = c.get(
        "/api/preproc/runs/run_demo/node/fmriprep_wf.anat_wf.smooth/pickle",
        params={"rel": "result_smooth.pklz"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "dict"
    assert body["value"]["n_iter"] == 3
    assert body["value"]["out_file"].endswith("x.nii.gz")


def test_pickle_returns_error_for_corrupt(app_with_run):
    app, _ = app_with_run
    c = TestClient(app)
    r = c.get(
        "/api/preproc/runs/run_demo/node/fmriprep_wf.anat_wf.smooth/pickle",
        params={"rel": "broken.pkl"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "error" in body


def test_pickle_refuses_non_pickle_suffix(app_with_run):
    app, _ = app_with_run
    c = TestClient(app)
    r = c.get(
        "/api/preproc/runs/run_demo/node/fmriprep_wf.anat_wf.smooth/pickle",
        params={"rel": "command.txt"},
    )
    assert r.status_code == 403


def test_404_when_run_unknown(tmp_path):
    from fmriflow.server.app import create_app
    app = create_app(derivatives_dir=str(tmp_path))
    c = TestClient(app)
    r = c.get(
        "/api/preproc/runs/no-such-run/node/wf.x/files",
    )
    assert r.status_code == 404


def test_409_when_run_has_no_work_dir(tmp_path):
    from fmriflow.server.app import create_app
    app = create_app(derivatives_dir=str(tmp_path))
    mgr: PreprocManager = app.state.preproc_manager
    mgr.active_runs["r"] = PreprocRunHandle(
        run_id="r", subject="01", backend="fmriprep", status="done",
        params={},  # no work_dir
    )
    c = TestClient(app)
    r = c.get("/api/preproc/runs/r/node/wf.x/files")
    assert r.status_code == 409


def test_finds_matching_crash_files(tmp_path):
    """When a run has crashes for the leaf, /files surfaces them."""
    from fmriflow.server.app import create_app

    work_dir = tmp_path / "work"
    output_dir = tmp_path / "out"
    leaf = work_dir / "fmriprep_wf" / "boom"
    leaf.mkdir(parents=True)
    log_dir = output_dir / "sub-01" / "log" / "20260505-150000"
    log_dir.mkdir(parents=True)
    (log_dir / "crash-20260505-boom-abc.txt").write_text("traceback...")
    (log_dir / "crash-20260505-other-abc.txt").write_text("unrelated")

    app = create_app(derivatives_dir=str(tmp_path))
    mgr: PreprocManager = app.state.preproc_manager
    mgr.active_runs["r"] = PreprocRunHandle(
        run_id="r", subject="01", backend="fmriprep", status="failed",
        params={"work_dir": str(work_dir), "output_dir": str(output_dir)},
    )
    c = TestClient(app)
    r = c.get("/api/preproc/runs/r/node/fmriprep_wf.boom/files")
    assert r.status_code == 200
    crashes = r.json()["crashes"]
    assert len(crashes) == 1
    assert crashes[0]["name"].startswith("crash-")
    assert "boom" in crashes[0]["name"]
