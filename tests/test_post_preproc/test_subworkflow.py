"""Run a graph that wraps a saved smooth workflow as a subworkflow node."""

from __future__ import annotations

from pathlib import Path

import pytest

nibabel = pytest.importorskip("nibabel")
np = pytest.importorskip("numpy")
pytest.importorskip("scipy")

from fmriflow.post_preproc.manifest import PostPreprocConfig
from fmriflow.post_preproc.runner import run_post_preproc
from fmriflow.preproc.manifest import PreprocManifest, RunRecord
from fmriflow.registry import ModuleRegistry
from fmriflow.server.services.post_preproc_workflow_store import (
    PostPreprocWorkflowStore,
)


def _write_nii(path: Path):
    affine = np.eye(4)
    affine[0, 0] = affine[1, 1] = affine[2, 2] = 2.0
    nibabel.Nifti1Image(np.zeros((4, 4, 4, 2), "float32"), affine).to_filename(str(path))


def test_subworkflow_runs_inner_smooth(tmp_path):
    bold = tmp_path / "bold.nii.gz"
    _write_nii(bold)

    src_manifest_path = tmp_path / "preproc_manifest.json"
    PreprocManifest(
        subject="01", dataset="ds", sessions=[],
        runs=[RunRecord(run_name="r1", source_file=str(bold),
                        output_file=str(bold), n_trs=2, shape=[4, 4, 4, 2])],
        backend="x", backend_version="0", parameters={}, space="MNI",
        output_dir=str(tmp_path),
    ).save(src_manifest_path)

    # Save an inner workflow with a single smooth node, exposing in_file/out_file.
    store = PostPreprocWorkflowStore(tmp_path / "wfs")
    inner_graph = {
        "nodes": [{
            "id": "smo", "type": "smooth",
            "data": {"params": {"fwhm": 4.0}}, "position": {},
        }],
        "edges": [],
    }
    store.save(
        "smooth_inner",
        inner_graph,
        inputs={"in_file": {"from": "smo.in_file"}},
        outputs={"out_file": {"from": "smo.out_file"}},
    )

    # Outer graph: subworkflow node, in_file fed via _inputs.
    outer_graph = {
        "nodes": [{
            "id": "sw", "type": "subworkflow",
            "data": {"params": {
                "workflow_name": "smooth_inner",
                "_inputs": {"in_file": str(bold)},
            }},
            "position": {},
        }],
        "edges": [],
    }

    config = PostPreprocConfig(
        subject="01",
        source_manifest_path=str(src_manifest_path),
        graph=outer_graph,
        output_dir=str(tmp_path / "post"),
    )
    registry = ModuleRegistry()
    registry.discover()

    result = run_post_preproc(config, registry=registry, workflow_store=store)
    sw_record = next(r for r in result.nodes_run if r.node_id == "sw")
    out_file = Path(sw_record.outputs["out_file"])
    assert out_file.is_file()


def test_subworkflow_cycle_detected(tmp_path):
    """If wf A includes wf A, we raise instead of recursing forever."""
    bold = tmp_path / "bold.nii.gz"
    _write_nii(bold)

    src_manifest_path = tmp_path / "preproc_manifest.json"
    PreprocManifest(
        subject="01", dataset="ds", sessions=[],
        runs=[RunRecord(run_name="r1", source_file=str(bold),
                        output_file=str(bold), n_trs=2, shape=[4, 4, 4, 2])],
        backend="x", backend_version="0", parameters={}, space="MNI",
        output_dir=str(tmp_path),
    ).save(src_manifest_path)

    store = PostPreprocWorkflowStore(tmp_path / "wfs")
    self_call = {
        "nodes": [{
            "id": "sw", "type": "subworkflow",
            "data": {"params": {"workflow_name": "loop"}}, "position": {},
        }],
        "edges": [],
    }
    store.save(
        "loop",
        self_call,
        inputs={"in_file": {"from": "sw.in_file"}},
        outputs={"out_file": {"from": "sw.out_file"}},
    )

    outer = {
        "nodes": [{
            "id": "sw", "type": "subworkflow",
            "data": {"params": {
                "workflow_name": "loop",
                "_inputs": {"in_file": str(bold)},
            }}, "position": {},
        }],
        "edges": [],
    }
    config = PostPreprocConfig(
        subject="01",
        source_manifest_path=str(src_manifest_path),
        graph=outer,
        output_dir=str(tmp_path / "post"),
    )
    registry = ModuleRegistry()
    registry.discover()

    with pytest.raises(RuntimeError, match="subworkflow cycle"):
        run_post_preproc(config, registry=registry, workflow_store=store)
