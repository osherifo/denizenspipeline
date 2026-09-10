"""PreprocRunManager + the detached CLI: launch, poll, manifest, resume, legacy rejection."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import numpy as np
import pytest

from tests.test_preproc.conftest import install_parked_nodes  # noqa: E402

nib = pytest.importorskip("nibabel")
nipype = pytest.importorskip("nipype")

from fmriflow.preproc.graph import Pipeline, PipelineNode, PipelineRunRequest  # noqa: E402
from fmriflow.preproc.node_registry import NodeRegistry  # noqa: E402
from fmriflow.server.services.pipeline_store import PipelineStore  # noqa: E402
from fmriflow.server.services.preproc_run_manager import PreprocRunManager  # noqa: E402
from fmriflow.server.services.run_registry import RunRegistry  # noqa: E402
from fmriflow.preproc.nodes._parked import PARKED_DIR  # noqa: E402


@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.setenv("FMRIFLOW_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("FMRIFLOW_INCLUDE_PARKED_NODES", "1")
    install_parked_nodes(tmp_path / "home")
    return PreprocRunManager(
        run_registry=RunRegistry(root=tmp_path / "runs"),
        pipeline_store=PipelineStore(tmp_path / "configs"),
        node_registry=NodeRegistry(include_parked=True, user_dirs=[PARKED_DIR]).discover(),
    )


def _tiny_pipeline(tmp_path) -> Pipeline:
    src = tmp_path / "in.nii.gz"
    nib.save(nib.Nifti1Image(np.zeros((2, 2, 2, 3), dtype="float32"), np.eye(4)), src)
    return Pipeline(
        name="tiny",
        nodes=[
            PipelineNode(id="ident", type="identity", literal_inputs={"in_file": str(src)}),
            PipelineNode(id="sm", type="smooth", params={"fwhm": 1.0}),
        ],
        edges=[{"id": "e", "source": "ident", "target": "sm", "sourceHandle": "out_file", "targetHandle": "in_file"}] and
              [__import__("fmriflow.preproc.graph", fromlist=["PipelineEdge"]).PipelineEdge(
                  id="e", source="ident", target="sm", source_handle="out_file", target_handle="in_file")],
        manifest={"backend_node": "ident", "bold_from": "sm.out_file"},
    )


def _wait(manager, run_id, timeout=90):
    t0 = time.time()
    while time.time() - t0 < timeout:
        s = manager.get_run(run_id)
        if s["status"] not in ("running",):
            return s
        time.sleep(0.5)
    raise AssertionError(f"run {run_id} still running after {timeout}s")


def test_detached_run_completes_with_manifest_and_events(manager, tmp_path):
    pipeline = _tiny_pipeline(tmp_path)
    req = PipelineRunRequest(subject="01", output_dir=str(tmp_path / "out"))
    run_id = manager.start_run(pipeline, req, pipeline_name="tiny")
    assert run_id.startswith("pp_")
    assert (manager.run_dir(run_id) / "job.json").exists()

    s = _wait(manager, run_id)
    assert s["status"] == "done", s
    assert s["pipeline"] == "tiny" and s["n_nodes"] == 2
    assert Path(s["manifest_path"]).is_file()
    assert (Path(req.output_dir) / "preproc_manifest.json").is_file()
    manifest = json.loads(Path(s["manifest_path"]).read_text())
    assert manifest["additional_steps"][0]["name"] == "smooth"
    assert s["result"]["status"] == "completed"
    assert Path(s["work_dir"]).is_dir()

    events = [json.loads(l) for l in manager.events_path(run_id).read_text().splitlines()]
    assert events[0]["event"] == "started" and events[-1]["event"] == "completed"
    status = manager.nipype_status(run_id)
    assert {n["leaf"] for n in status["recent_nodes"]} == {"ident", "sm"}
    assert all(n["status"] == "ok" for n in status["recent_nodes"])


def test_resume_reuses_work_dir_and_caches(manager, tmp_path):
    pipeline = _tiny_pipeline(tmp_path)
    req = PipelineRunRequest(subject="01", output_dir=str(tmp_path / "out"))
    first = manager.start_run(pipeline, req)
    _wait(manager, first)
    second = manager.resume_run(first)
    s = _wait(manager, second)
    assert s["status"] == "done" and s["resumed_from"] == first
    assert {n["status"] for n in s["result"]["nodes"]} == {"cached"}
    third = manager.restart_run(first)
    s3 = _wait(manager, third)
    assert {n["status"] for n in s3["result"]["nodes"]} == {"ok"}


def test_cancel_marks_cancelled(manager, tmp_path):
    pipeline = Pipeline(
        name="slow",
        nodes=[PipelineNode(id="sh", type="custom_shell", kind="container_app", params={"command": "sleep 30", "file_pattern": "*.none"})],
        manifest={},
    )
    run_id = manager.start_run(pipeline, PipelineRunRequest(subject="01", output_dir=str(tmp_path / "o")))
    time.sleep(2.0)
    out = manager.cancel_run(run_id)
    assert out["cancelled"]
    time.sleep(1.0)
    assert manager.get_run(run_id)["status"] == "cancelled"


def test_start_from_config_file_by_name_and_legacy_rejected(manager, tmp_path):
    pipeline = _tiny_pipeline(tmp_path)
    manager.pipeline_store.save("tiny", pipeline)
    cfg = tmp_path / "stage.yaml"
    cfg.write_text(f"preproc:\n  pipeline: tiny\n  subject: '01'\n  output_dir: {tmp_path / 'out2'}\n")
    run_id = manager.start_run_from_config_file(str(cfg))
    assert _wait(manager, run_id)["status"] == "done"

    legacy = tmp_path / "legacy.yaml"
    legacy.write_text("preproc:\n  backend: fmriprep\n  subject: '01'\n  output_dir: /x\n  backend_params: {mode: anat_only}\n")
    with pytest.raises(ValueError, match="fmriflow preproc migrate"):
        manager.start_run_from_config_file(str(legacy))


def test_list_and_delete(manager, tmp_path):
    pipeline = _tiny_pipeline(tmp_path)
    run_id = manager.start_run(pipeline, PipelineRunRequest(subject="01", output_dir=str(tmp_path / "out")))
    _wait(manager, run_id)
    assert any(r["run_id"] == run_id for r in manager.list_runs())
    assert manager.delete_run(run_id)
    assert manager.get_run(run_id) is None


def test_validation_failure_does_not_spawn(manager, tmp_path):
    pipeline = Pipeline(name="bad", nodes=[PipelineNode(id="x", type="nope")])
    with pytest.raises(ValueError):
        manager.start_run(pipeline, PipelineRunRequest(subject="01", output_dir=str(tmp_path)))
    assert manager.list_runs() == []
