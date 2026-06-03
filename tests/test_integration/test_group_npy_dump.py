"""Tests for the ``group_npy_dump`` reporter."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from fmriflow.core.group_types import GroupResult
from fmriflow.core.types import SemanticSubspace
from fmriflow.modules.group_reporters.group_npy_dump import GroupNpyDumpReporter


def test_dumps_ndarrays_subspaces_and_scalars(tmp_path: Path):
    g = GroupResult(group_name="demo")
    g.put("group.mean", np.array([1.0, 2.0, 3.0]))
    g.put("group.count", np.array([5, 5, 4], dtype=np.int32))
    g.put("group.basis", SemanticSubspace(
        basis=np.eye(10)[:, :3].astype(np.float64),
        singular_values=np.array([3.0, 2.0, 1.0]),
        feature="english1000", n_delays=2, feature_dim=5,
        metadata={"subjects": ["S1", "S2"]},
    ))
    g.put("group.acc", {"mean": 0.42, "sem": 0.05, "n_subjects": 2})
    g.put("group.n_subjects", 3)

    reporter = GroupNpyDumpReporter()
    saved = reporter.report(g, {
        "output_dir": str(tmp_path),
        "group_report": [{"name": "group_npy_dump"}],
    })

    outdir = tmp_path / "group_artifacts"
    assert outdir.is_dir()

    # ndarray artifacts
    mean = np.load(outdir / "group.mean.npy")
    np.testing.assert_allclose(mean, [1.0, 2.0, 3.0])

    count = np.load(outdir / "group.count.npy")
    np.testing.assert_array_equal(count, [5, 5, 4])

    # SemanticSubspace: .npy (basis) + .json (meta)
    basis = np.load(outdir / "group.basis.npy")
    assert basis.shape == (10, 3)
    meta = json.loads((outdir / "group.basis.json").read_text())
    assert meta["feature"] == "english1000"
    assert meta["n_components"] == 3
    assert meta["singular_values"] == [3.0, 2.0, 1.0]
    assert meta["metadata"]["subjects"] == ["S1", "S2"]

    # Scalars/dicts coalesced into scalars.json
    scalars = json.loads((outdir / "scalars.json").read_text())
    assert scalars["group.acc"] == {"mean": 0.42, "sem": 0.05, "n_subjects": 2}
    assert scalars["group.n_subjects"] == 3

    # Returned manifest
    assert saved["group.mean"].endswith("group.mean.npy")
    assert "group.basis.meta" in saved
    assert saved["__scalars__"].endswith("scalars.json")


def test_safe_key_sanitisation(tmp_path):
    g = GroupResult(group_name="demo")
    g.put("group.result.scores/with/slashes", np.zeros(3))
    GroupNpyDumpReporter().report(g, {"output_dir": str(tmp_path)})
    files = sorted(p.name for p in (tmp_path / "group_artifacts").iterdir())
    assert "group.result.scores_with_slashes.npy" in files


def test_no_artifacts(tmp_path):
    g = GroupResult(group_name="demo")
    saved = GroupNpyDumpReporter().report(g, {"output_dir": str(tmp_path)})
    assert saved == {}
    # Output dir is still created (cheap; matches html reporter behaviour)
    assert (tmp_path / "group_artifacts").is_dir()
