"""Run a small smooth-only post-preproc graph against a stub PreprocManifest."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

nibabel = pytest.importorskip("nibabel")
np = pytest.importorskip("numpy")
pytest.importorskip("scipy")

from fmriflow.post_preproc.manifest import PostPreprocConfig
from fmriflow.post_preproc.runner import run_post_preproc
from fmriflow.preproc.manifest import PreprocManifest, RunRecord
from fmriflow.registry import ModuleRegistry


def _write_nii(path: Path, shape=(4, 4, 4, 3)):
    affine = np.eye(4)
    affine[0, 0] = affine[1, 1] = affine[2, 2] = 2.0  # 2 mm voxels
    data = np.random.RandomState(0).rand(*shape).astype("float32")
    nibabel.Nifti1Image(data, affine).to_filename(str(path))


def test_smooth_only_pipeline(tmp_path):
    # Stub upstream PreprocManifest + a fake BOLD nifti.
    out_dir = tmp_path / "deriv"
    (out_dir / "sub-01").mkdir(parents=True)
    bold = out_dir / "sub-01" / "bold_run01.nii.gz"
    _write_nii(bold)

    manifest = PreprocManifest(
        subject="01",
        dataset="ds-test",
        sessions=[],
        runs=[RunRecord(
            run_name="run01",
            source_file=str(bold),
            output_file=str(bold.relative_to(out_dir)),
            n_trs=3,
            shape=[4, 4, 4, 3],
        )],
        backend="fmriprep",
        backend_version="0.0.0",
        parameters={},
        space="MNI",
        output_dir=str(out_dir),
    )
    src_manifest_path = out_dir / "preproc_manifest.json"
    src_manifest_path.write_text(manifest.to_json())

    graph = {
        "nodes": [
            {"id": "src", "type": "preproc_run",
             "data": {"params": {"run_name": "run01"}}, "position": {}},
            {"id": "smo", "type": "smooth",
             "data": {"params": {"fwhm": 4.0}}, "position": {}},
        ],
        "edges": [
            {"id": "e1", "source": "src", "target": "smo",
             "sourceHandle": "out_file", "targetHandle": "in_file"},
        ],
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

    # Manifest contains both nodes' run records.
    assert {r.node_id for r in result.nodes_run} == {"src", "smo"}
    smo_record = next(r for r in result.nodes_run if r.node_id == "smo")
    out_file = Path(smo_record.outputs["out_file"])
    assert out_file.is_file()

    # Output is a valid NIfTI of the same shape.
    out_img = nibabel.load(str(out_file))
    assert out_img.shape == (4, 4, 4, 3)

    # Manifest JSON is on disk.
    disk = json.loads((Path(config.output_dir) / "post_preproc_manifest.json").read_text())
    assert disk["subject"] == "01"
    assert len(disk["nodes_run"]) == 2
