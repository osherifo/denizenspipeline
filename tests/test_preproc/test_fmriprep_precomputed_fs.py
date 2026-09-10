"""func_precomputed_anat: reuse a FreeSurfer subject on a staged copy, never in place."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

nib = pytest.importorskip("nibabel")

from fmriflow.preproc import checkpoints as ck  # noqa: E402
from fmriflow.preproc.nodes.fmriprep import FmriprepNode  # noqa: E402


def _recon(root: Path, name: str) -> Path:
    d = root / name
    for f in FmriprepNode.FS_REQUIRED:
        (d / f).parent.mkdir(parents=True, exist_ok=True)
        (d / f).write_bytes(b"x")
    (d / "scripts").mkdir(exist_ok=True)
    (d / "scripts" / "IsRunning.lh+rh").write_text("stale lock")
    return d


def test_precomputed_subject_is_staged_as_a_copy(tmp_path):
    root = tmp_path / "fs"; _recon(root, "sub01fs"); (root / "fsaverage").mkdir()
    bids = tmp_path / "bids"; bids.mkdir()
    work = tmp_path / "work"
    node = FmriprepNode()
    inputs = {"bids_dir": str(bids), "subject": "01", "output_dir": str(tmp_path / "out"), "work_dir": str(work), "fs_subjects_dir": str(root)}
    params = {"mode": "func_precomputed_anat", "fs_subject": "sub01fs"}
    assert not [e for e in node.validate(inputs, params) if "precomputed" in e or "fs_subject" in e]
    cmd = node.build_command(inputs, params, tmp_path / "node")
    staged = work / "fs_subjects"
    assert cmd[cmd.index("--fs-subjects-dir") + 1] == str(staged)
    assert (staged / "sub-01" / "surf" / "lh.white").is_file() and not (staged / "sub-01").is_symlink()
    assert not (staged / "sub-01" / "scripts" / "IsRunning.lh+rh").exists()      # stale lock dropped
    assert (staged / "fsaverage").is_symlink()
    assert (staged / "sub-01" / ".fmriflow_staged_from").read_text() == str((root / "sub01fs").resolve())
    # writing into the copy leaves the original alone
    (staged / "sub-01" / "surf" / "lh.thickness").write_bytes(b"new")
    assert not (root / "sub01fs" / "surf" / "lh.thickness").exists()
    # a second build reuses the staged copy instead of re-copying
    (staged / "sub-01" / "marker").write_text("keep")
    node.build_command(inputs, params, tmp_path / "node")
    assert (staged / "sub-01" / "marker").exists()
    # the checkpoint context points at the staged subject
    ctx = node.checkpoint_context(inputs, params, tmp_path / "node")
    assert ctx["fs_subject_dir"] == str(staged / "sub-01")


def test_missing_or_incomplete_precomputed_subject_fails_fast(tmp_path):
    root = tmp_path / "fs"; _recon(root, "sub01fs"); (root / "sub-02").mkdir()
    bids = tmp_path / "bids"; bids.mkdir()
    node = FmriprepNode()
    inputs = {"bids_dir": str(bids), "subject": "01", "fs_subjects_dir": str(root)}
    errs = node.validate(inputs, {"mode": "func_precomputed_anat"})            # expects sub-01, absent
    assert any("no precomputed FreeSurfer subject 'sub-01'" in e and "sub01fs" in e for e in errs), errs
    errs = node.validate(inputs, {"mode": "func_precomputed_anat", "fs_subject": "sub-02"})   # present but empty
    assert any("incomplete" in e and "surf/lh.white" in e for e in errs), errs
    errs = node.validate(inputs, {"mode": "func_precomputed_anat", "fs_subject": "sub01fs"})
    assert not any("precomputed" in e for e in errs), errs


def test_singleton_time_axis_counts_as_one_volume(tmp_path):
    ref = tmp_path / "sub-01_desc-coreg_boldref.nii.gz"
    nib.save(nib.Nifti1Image(np.random.default_rng(0).normal(100, 5, (4, 4, 4, 1)).astype("float32"), np.eye(4)), str(ref))
    m, _ = ck.bold_integrity_metrics(ref)
    assert m["is_4d"] is False and m["n_trs"] == 1 and m["shape"] == [4, 4, 4, 1]
    from fmriflow.preproc.norms import norms_for
    assert ck.verdict_for(m, norms_for("boldref_single_volume"))[0] == "ok"
    n, _ = ck.nifti_stats_metrics(ref)
    assert n["is_4d"] is False and n["n_trs"] == 1
    o, _ = ck.output_file_metrics(ref)
    assert o["is_4d"] is False
