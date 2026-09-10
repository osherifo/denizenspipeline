"""/api/preproc/runs/{id}/nodes/{node_id}/... — one node of one run, run-scoped files."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from fmriflow.server.services.run_registry import RunStateFile


@pytest.fixture
def app_with_fmriprep_run(tmp_path, monkeypatch):
    monkeypatch.setenv("FMRIFLOW_HOME", str(tmp_path / "home"))
    from fmriflow.server.app import create_app

    wf = "p__sub_01"
    work = tmp_path / "work"
    node_dir = work / wf / "fp"
    node_dir.mkdir(parents=True)
    (node_dir / "stdout.log").write_text("\n".join(f"line {i}" for i in range(10)) + "\n")
    # an inner nipype leaf on disk (for work_tree?prefix=)
    (node_dir / "fmriprep_wf" / "single_subject_01_wf" / "anat_preproc_wf" / "brain_extraction_wf" / "n4").mkdir(parents=True)
    (node_dir / "fmriprep_wf" / "single_subject_01_wf" / "anat_preproc_wf" / "brain_extraction_wf" / "n4" / "_node.pklz").write_bytes(b"x")

    deriv = tmp_path / "deriv"
    (deriv / "sub-01" / "figures").mkdir(parents=True)
    (deriv / "sub-01.html").write_text("<html><img src='sub-01/figures/a.svg'></html>")
    (deriv / "sub-01" / "figures" / "a.svg").write_text("<svg/>")
    (deriv / "sub-01" / "figures" / "evil.py").write_text("print()")
    fs = deriv / "sourcedata" / "freesurfer" / "sub-01"
    (fs / "mri").mkdir(parents=True); (fs / "surf").mkdir()
    (fs / "mri" / "T1.mgz").write_bytes(b"mgz"); (fs / "surf" / "lh.pial").write_bytes(b"pial")
    manifest = node_dir / "preproc_manifest.json"
    manifest.write_text(json.dumps({"subject": "01", "dataset": "ds", "backend": "fmriprep", "backend_version": "24.1.1", "runs": []}))

    app = create_app(derivatives_dir=str(tmp_path / "derivatives"))
    mgr = app.state.preproc_run_manager
    state = RunStateFile(
        run_id="run1", kind="preproc", backend="pipeline", subject="01", status="done",
        params={"pipeline": "p", "workflow": wf, "work_dir": str(work), "output_dir": str(deriv),
                "nodes": [{"id": "fp", "type": "fmriprep", "kind": "container_app"},
                          {"id": "later", "type": "smooth", "kind": "interface"}], "n_nodes": 2},
        result={"status": "completed", "duration_s": 5.0, "errors": [], "nodes": [{
            "node_id": "fp", "node_type": "fmriprep", "kind": "container_app", "status": "ok", "duration_s": 4.0,
            "work_dir": str(node_dir), "error": None,
            "outputs": {"derivatives_dir": str(deriv), "report_html": str(deriv / "sub-01.html"),
                        "fs_subjects_dir": str(deriv / "sourcedata" / "freesurfer"), "manifest": str(manifest)},
        }]},
    )
    mgr.registry.register(state); mgr.registry.update(state)
    run_dir = mgr.run_dir("run1")
    (run_dir / "job.json").write_text(json.dumps({
        "pipeline": {"name": "p", "nodes": [{"id": "fp", "type": "fmriprep", "kind": "container_app", "data": {"params": {"mode": "anat_only"}}},
                                             {"id": "later", "type": "smooth", "kind": "interface", "data": {"params": {"fwhm": 5}}}],
                     "edges": [], "manifest": {"backend_node": "fp"}},
        "request": {"subject": "01", "dataset": "ds"},
    }))
    ev = [
        {"event": "node_start", "node": f"{wf}.fp", "leaf": "fp", "workflow": wf, "t": 1.0},
        {"event": "node_start", "node": f"{wf}.fp.fmriprep_wf.single_subject_01_wf.anat_preproc_wf.n4", "leaf": "n4",
         "workflow": f"{wf}.fp.fmriprep_wf.single_subject_01_wf.anat_preproc_wf", "t": 2.0, "inner": True},
        {"event": "node_done", "node": f"{wf}.fp.fmriprep_wf.single_subject_01_wf.anat_preproc_wf.n4", "leaf": "n4",
         "workflow": f"{wf}.fp.fmriprep_wf.single_subject_01_wf.anat_preproc_wf", "t": 3.0, "inner": True},
        {"event": "node_start", "node": f"{wf}.later", "leaf": "later", "workflow": wf, "t": 4.0},
    ]
    (run_dir / "events.jsonl").write_text("\n".join(json.dumps(e) for e in ev) + "\n")
    return app


def test_record_merges_result_job_and_library(app_with_fmriprep_run):
    c = TestClient(app_with_fmriprep_run)
    r = c.get("/api/preproc/runs/run1/nodes/fp")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["node_type"] == "fmriprep" and d["status"] == "ok" and d["has_log"] is True
    assert d["params"] == {"mode": "anat_only"}
    assert d["ui"]["inner_dag"] is True and d["ui"]["report"] == "report_html"
    assert d["ui"]["structural_qc"] == "fs_subjects_dir" and d["ui"]["summary"] == "manifest"
    assert d["ui"]["label_map"] == "fmriprep" and d["subject"] == "01" and d["dataset"] == "ds"
    assert "report_html" in d["output_ports"] and d["output_ports"]["report_html"]["kind"] == "html"

    # a node the runner has not reached yet is synthesised as pending
    later = c.get("/api/preproc/runs/run1/nodes/later").json()
    assert later["status"] == "pending" and later["outputs"] == {} and later["node_type"] == "smooth"
    assert later["ui"]["inner_dag"] is False and later["ui"]["report"] is None
    assert c.get("/api/preproc/runs/run1/nodes/nope").status_code == 404
    assert c.get("/api/preproc/runs/nope/nodes/fp").status_code == 404


def test_functional_only_run_hides_structural_qc(app_with_fmriprep_run):
    """The FreeSurfer dir a functional run reads was made by the anatomical run; the popup
    must not offer structural QC for it."""
    app = app_with_fmriprep_run
    run_dir = app.state.preproc_run_manager.run_dir("run1")
    job = json.loads((run_dir / "job.json").read_text())
    job["pipeline"]["nodes"][0]["data"]["params"] = {"mode": "func_precomputed_anat"}
    (run_dir / "job.json").write_text(json.dumps(job))
    d = TestClient(app).get("/api/preproc/runs/run1/nodes/fp").json()
    assert d["ui"]["structural_qc"] is None and d["ui"]["report"] == "report_html"


def test_log_inner_and_work_tree_are_node_scoped(app_with_fmriprep_run):
    c = TestClient(app_with_fmriprep_run)
    log = c.get("/api/preproc/runs/run1/nodes/fp/log?tail=3").json()
    assert log["total"] == 10 and log["lines"] == ["line 7", "line 8", "line 9"]

    inner = c.get("/api/preproc/runs/run1/nodes/fp/inner").json()
    assert inner["prefix"] == "p__sub_01.fp."
    nodes = inner["nipype_status"]["recent_nodes"]
    assert [n["node"] for n in nodes] == ["fmriprep_wf.single_subject_01_wf.anat_preproc_wf.n4"]
    assert nodes[0]["workflow"] == "fmriprep_wf.single_subject_01_wf.anat_preproc_wf"
    assert nodes[0]["status"] == "ok" and inner["nipype_status"]["counts"]["total_seen"] == 1

    tree = c.get("/api/preproc/runs/run1/work_tree", params={"prefix": "p__sub_01.fp."}).json()
    assert tree["leaves"] == ["fmriprep_wf.single_subject_01_wf.anat_preproc_wf.brain_extraction_wf.n4"]


def test_report_manifest_and_fs_files_are_served_safely(app_with_fmriprep_run):
    c = TestClient(app_with_fmriprep_run)
    r = c.get("/api/preproc/runs/run1/nodes/fp/report/")
    assert r.status_code == 200 and "sub-01/figures/a.svg" in r.text
    assert c.get("/api/preproc/runs/run1/nodes/fp/report/sub-01/figures/a.svg").status_code == 200
    assert c.get("/api/preproc/runs/run1/nodes/fp/report/sub-01/figures/evil.py").status_code == 403
    assert c.get("/api/preproc/runs/run1/nodes/fp/report/../../work/p__sub_01/fp/stdout.log").status_code in (403, 404)

    assert c.get("/api/preproc/runs/run1/nodes/fp/manifest").json()["backend_version"] == "24.1.1"
    assert c.get("/api/preproc/runs/run1/nodes/fp/fs-file", params={"rel": "mri/T1.mgz"}).status_code == 200
    assert c.get("/api/preproc/runs/run1/nodes/fp/fs-file", params={"rel": "mri/T1.py"}).status_code == 403
    assert c.get("/api/preproc/runs/run1/nodes/fp/fs-file", params={"rel": "mri/nope.mgz"}).status_code == 404
    fv = c.get("/api/preproc/runs/run1/nodes/fp/freeview-command").json()
    assert "T1.mgz" in fv["command"] and "lh.pial" in fv["command"]

    # a node without the capability answers 404, not a crash
    assert c.get("/api/preproc/runs/run1/nodes/later/report/").status_code == 404
    assert c.get("/api/preproc/runs/run1/nodes/later/manifest").status_code == 404
