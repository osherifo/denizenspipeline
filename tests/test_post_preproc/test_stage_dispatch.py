"""PostPreprocManager.start_run_from_config_file → WorkflowManager fan-in."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

nibabel = pytest.importorskip("nibabel")
np = pytest.importorskip("numpy")
pytest.importorskip("scipy")
yaml = pytest.importorskip("yaml")

from fmriflow.preproc.manifest import PreprocManifest, RunRecord
from fmriflow.registry import ModuleRegistry
from fmriflow.server.services.post_preproc_manager import PostPreprocManager
from fmriflow.server.services.post_preproc_workflow_store import (
    PostPreprocWorkflowStore,
)


def _write_nii(path: Path):
    affine = np.eye(4)
    affine[0, 0] = affine[1, 1] = affine[2, 2] = 2.0
    nibabel.Nifti1Image(np.zeros((4, 4, 4, 2), "float32"), affine).to_filename(str(path))


def test_start_run_from_config_file_runs_saved_graph(tmp_path):
    bold = tmp_path / "bold.nii.gz"
    _write_nii(bold)

    src = tmp_path / "preproc_manifest.json"
    PreprocManifest(
        subject="01", dataset="ds", sessions=[],
        runs=[RunRecord(run_name="r1", source_file=str(bold),
                        output_file=str(bold), n_trs=2, shape=[4, 4, 4, 2])],
        backend="x", backend_version="0", parameters={}, space="MNI",
        output_dir=str(tmp_path),
    ).save(src)

    store = PostPreprocWorkflowStore(tmp_path / "wfs")
    store.save(
        "smooth_only",
        {
            "nodes": [{
                "id": "smo", "type": "smooth",
                "data": {"params": {"fwhm": 4.0}}, "position": {},
            }],
            "edges": [],
        },
        inputs={"in_file": {"from": "smo.in_file"}},
        outputs={"out_file": {"from": "smo.out_file"}},
    )

    # Stage YAML referencing the saved graph.
    stage_yaml = tmp_path / "stage.yaml"
    stage_yaml.write_text(yaml.safe_dump({
        "graph": "smooth_only",
        "subject": "01",
        "source_manifest_path": str(src),
        "output_dir": str(tmp_path / "post"),
        "bindings": {"in_file": {"source_run": "r1"}},
    }))

    registry = ModuleRegistry()
    registry.discover()
    mgr = PostPreprocManager()
    mgr.bind_dependencies(registry=registry, workflow_store=store)

    run_id = mgr.start_run_from_config_file(str(stage_yaml))
    # WorkflowManager polls active_runs until status leaves "running".
    deadline = time.time() + 30
    while time.time() < deadline:
        h = mgr.active_runs.get(run_id)
        assert h is not None
        if h.status in ("done", "failed"):
            break
        time.sleep(0.1)
    h = mgr.active_runs[run_id]
    assert h.status == "done", h.error
    assert h.manifest is not None
    assert any(r["node_type"] == "smooth" for r in h.manifest["nodes_run"])
