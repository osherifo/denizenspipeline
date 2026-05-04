"""Literal _inputs path overrides for nodes without an upstream edge."""

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


def _write_nii(path: Path):
    affine = np.eye(4)
    affine[0, 0] = affine[1, 1] = affine[2, 2] = 2.0
    nibabel.Nifti1Image(np.zeros((4, 4, 4, 2), "float32"), affine).to_filename(str(path))


def test_smooth_with_literal_input_path(tmp_path):
    bold = tmp_path / "bold.nii.gz"
    _write_nii(bold)

    # Stub manifest just so the runner can read the dataset name.
    src_manifest = tmp_path / "preproc_manifest.json"
    PreprocManifest(
        subject="01",
        dataset="ds-test",
        sessions=[],
        runs=[RunRecord(run_name="r1", source_file=str(bold),
                        output_file=str(bold), n_trs=2, shape=[4, 4, 4, 2])],
        backend="fmriprep", backend_version="0", parameters={}, space="MNI",
        output_dir=str(tmp_path),
    ).save(src_manifest)

    # No source node, no edges — the smooth node receives in_file via _inputs.
    graph = {
        "nodes": [
            {"id": "smo", "type": "smooth",
             "data": {"params": {"fwhm": 4.0, "_inputs": {"in_file": str(bold)}}},
             "position": {}},
        ],
        "edges": [],
    }

    config = PostPreprocConfig(
        subject="01",
        source_manifest_path=str(src_manifest),
        graph=graph,
        output_dir=str(tmp_path / "post"),
    )
    registry = ModuleRegistry()
    registry.discover()

    result = run_post_preproc(config, registry=registry)
    out = Path(result.nodes_run[0].outputs["out_file"])
    assert out.is_file()
