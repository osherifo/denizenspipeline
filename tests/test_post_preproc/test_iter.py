"""Iterate a smooth node over every run in the source manifest."""

from __future__ import annotations

from pathlib import Path

import pytest

nibabel = pytest.importorskip("nibabel")
np = pytest.importorskip("numpy")
pytest.importorskip("scipy")

from fmriflow.post_preproc.graph import PostPreprocGraph
from fmriflow.post_preproc.manifest import PostPreprocConfig
from fmriflow.post_preproc.runner import run_post_preproc
from fmriflow.preproc.manifest import PreprocManifest, RunRecord
from fmriflow.registry import ModuleRegistry


def _write_nii(path: Path):
    affine = np.eye(4)
    affine[0, 0] = affine[1, 1] = affine[2, 2] = 2.0
    nibabel.Nifti1Image(np.zeros((4, 4, 4, 2), "float32"), affine).to_filename(str(path))


def test_iter_over_source_manifest_runs(tmp_path):
    bolds = [tmp_path / f"bold_{i}.nii.gz" for i in range(2)]
    for b in bolds:
        _write_nii(b)

    src_manifest_path = tmp_path / "preproc_manifest.json"
    PreprocManifest(
        subject="01", dataset="ds", sessions=[],
        runs=[
            RunRecord(run_name=f"r{i}", source_file=str(b),
                      output_file=str(b), n_trs=2, shape=[4, 4, 4, 2])
            for i, b in enumerate(bolds)
        ],
        backend="x", backend_version="0", parameters={}, space="MNI",
        output_dir=str(tmp_path),
    ).save(src_manifest_path)

    graph = {
        "nodes": [{
            "id": "smo", "type": "smooth",
            "data": {"params": {
                "fwhm": 4.0,
                "_iter": {"handle": "in_file", "from_source_manifest": True},
            }},
            "position": {},
        }],
        "edges": [],
    }

    config = PostPreprocConfig(
        subject="01",
        source_manifest_path=str(src_manifest_path),
        graph=graph,
        output_dir=str(tmp_path / "post"),
    )
    registry = ModuleRegistry()
    registry.discover()

    result = run_post_preproc(config, registry=registry)
    smo_record = next(r for r in result.nodes_run if r.node_id == "smo")
    out_files = smo_record.outputs["out_file"].split(",")
    assert len(out_files) == 2
    for f in out_files:
        assert Path(f).is_file()


def test_iter_validates_handle_and_sink():
    g = PostPreprocGraph.from_reactflow({
        "nodes": [
            {"id": "src", "type": "preproc_run",
             "data": {"params": {"run_name": "r0"}}, "position": {}},
            {"id": "smo", "type": "smooth",
             "data": {"params": {"fwhm": 4.0,
                                 "_iter": {"handle": "wrong_handle"}}}, "position": {}},
        ],
        "edges": [
            {"id": "e1", "source": "src", "target": "smo",
             "sourceHandle": "out_file", "targetHandle": "in_file"},
            # Add an outgoing edge from the iterating node to a 3rd node.
        ],
    })
    g.nodes.append(type(g.nodes[0])(id="x", type="smooth", params={}, position={}))
    g.edges.append(type(g.edges[0])(
        id="e2", source="smo", target="x",
        source_handle="out_file", target_handle="in_file",
    ))
    from fmriflow.modules.nipype_nodes.smooth import SmoothNode
    from fmriflow.modules.nipype_nodes.source import PreprocRunSourceNode
    errors = g.validate_against({
        "smooth": SmoothNode,
        "preproc_run": PreprocRunSourceNode,
    })
    assert any("_iter handle" in e for e in errors)
    assert any("outgoing edges" in e for e in errors)
