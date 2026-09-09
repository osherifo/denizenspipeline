"""A failed run exposes its cause, full tracebacks and crash files over HTTP."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fmriflow.server.services.run_registry import RunStateFile

TRACE = (
    "NodeExecutionError: Exception raised while executing Node fmriprep.\n\n"
    "Traceback:\n\tTraceback (most recent call last):\n"
    "\t  File \"core.py\", line 402, in run\n\t    runtime = self._run_interface(runtime)\n"
    "\tValueError: fmriprep: mode 'func_precomputed_anat' requires fs_subjects_dir\n"
)


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("FMRIFLOW_HOME", str(tmp_path / "home"))
    from fmriflow.server.app import create_app
    return create_app(derivatives_dir=str(tmp_path / "derivatives"))


def _failed_run(app, run_id="pp_x"):
    mgr = app.state.preproc_run_manager
    state = RunStateFile(
        run_id=run_id, kind="preproc", backend="pipeline", subject="01", status="failed",
        error="NodeExecutionError: Exception raised while executing Node fmriprep.; node fmriprep failed",
        params={"pipeline": "p", "nodes": [], "n_nodes": 1},
        result={"status": "failed", "duration_s": 0.5, "errors": [TRACE], "nodes": []},
    )
    mgr.registry.register(state)
    mgr.registry.update(state)
    crash = mgr.run_dir(run_id) / "crash"
    crash.mkdir(parents=True, exist_ok=True)
    (crash / "crash-20260101-fmriprep-abc.txt").write_text("Node: p__sub_01.fmriprep\nWorking directory: /w\n\nTraceback...\n")
    return mgr


def test_detail_carries_cause_errors_and_crashes(app):
    _failed_run(app)
    c = TestClient(app)
    d = c.get("/api/preproc/runs/pp_x").json()
    assert d["cause"] == "ValueError: fmriprep: mode 'func_precomputed_anat' requires fs_subjects_dir"
    assert d["errors"] == [TRACE]
    assert d["crashes"] == [{"name": "crash-20260101-fmriprep-abc.txt", "size": d["crashes"][0]["size"], "node": "p__sub_01.fmriprep"}]

    r = c.get("/api/preproc/runs/pp_x/crashes/crash-20260101-fmriprep-abc.txt")
    assert r.status_code == 200 and r.json()["text"].startswith("Node: p__sub_01.fmriprep")
    assert c.get("/api/preproc/runs/pp_x/crashes/../state.json").status_code in (404, 422)
    assert c.get("/api/preproc/runs/pp_x/crashes/nope.txt").status_code == 404


def test_cause_falls_back_to_state_error_without_result(app):
    mgr = app.state.preproc_run_manager
    state = RunStateFile(run_id="pp_y", kind="preproc", backend="pipeline", subject="01", status="failed",
                         error="boom", params={"pipeline": "p", "nodes": [], "n_nodes": 0})
    mgr.registry.register(state); mgr.registry.update(state)
    d = TestClient(app).get("/api/preproc/runs/pp_y").json()
    assert d["errors"] == ["boom"] and d["cause"] == "boom" and d["crashes"] == []
