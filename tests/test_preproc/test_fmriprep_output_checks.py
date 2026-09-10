"""fmriprep's functional-output checks: per-run globbing, and the five metrics behind them."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

nib = pytest.importorskip("nibabel")

from fmriflow.preproc import checkpoints as ck  # noqa: E402
from fmriflow.preproc.nodes.fmriprep import FmriprepNode  # noqa: E402
from fmriflow.preproc.norms import norms_for  # noqa: E402


def _bold(path: Path, *, n_t=30, nan=False, zero_vol=False, spike=False, seed=0) -> Path:
    rng = np.random.default_rng(seed)
    data = 1000 + rng.normal(0, 5, (6, 6, 6, n_t))
    if nan:
        data[1, 1, 1, 3] = np.nan
    if zero_vol:
        data[..., 5] = 0
    if spike:
        data[..., 10] *= 3
    nib.save(nib.Nifti1Image(data.astype("float32"), np.eye(4)), str(path))
    return path


def _confounds(path: Path, *, fd_scale=0.1, trans_mm=0.3, n=30) -> Path:
    rng = np.random.default_rng(1)
    cols = ["framewise_displacement", "dvars", "trans_x", "trans_y", "trans_z", "rot_x", "rot_y", "rot_z",
            "a_comp_cor_00", "a_comp_cor_01", "t_comp_cor_00"]
    rows = []
    for i in range(n):
        fd = "n/a" if i == 0 else f"{abs(rng.normal(fd_scale, fd_scale / 3)):.4f}"
        rows.append([fd, f"{rng.normal(30, 2):.3f}"] + [f"{rng.uniform(-trans_mm, trans_mm):.4f}"] * 3 + [f"{rng.uniform(-0.002, 0.002):.5f}"] * 3
                    + [f"{rng.normal():.4f}", f"{rng.normal():.4f}", f"{rng.normal():.4f}"])
    path.write_text("\t".join(cols) + "\n" + "\n".join("\t".join(r) for r in rows) + "\n")
    path.with_suffix(".json").write_text(json.dumps({
        "a_comp_cor_00": {"CumulativeVarianceExplained": 0.31, "Mask": "combined", "Retained": True},
        "a_comp_cor_01": {"CumulativeVarianceExplained": 0.52, "Mask": "combined", "Retained": True},
        "t_comp_cor_00": {"CumulativeVarianceExplained": 0.2, "Mask": "temporal", "Retained": True},
    }))
    return path


def test_bold_integrity_flags_nan_zero_volume_and_spike(tmp_path):
    m, _ = ck.bold_integrity_metrics(_bold(tmp_path / "ok.nii.gz"))
    assert m["n_nan_inf"] == 0 and m["n_zero_volumes"] == 0 and m["n_spike_volumes"] == 0 and m["n_trs"] == 30
    assert ck.verdict_for(m, norms_for("bold_nan_inf"))[0] == "ok"
    assert ck.verdict_for(m, norms_for("bold_spikes"))[0] == "ok"
    m, _ = ck.bold_integrity_metrics(_bold(tmp_path / "bad.nii.gz", nan=True, zero_vol=True, spike=True))
    assert m["n_nan_inf"] == 1 and m["n_zero_volumes"] == 1 and m["n_spike_volumes"] >= 1 and 10 in m["spike_volumes"]
    assert ck.verdict_for(m, norms_for("bold_nan_inf"))[0] == "bad"
    assert ck.verdict_for(m, norms_for("bold_spikes"))[0] == "bad"     # the dead volume


def test_confounds_motion_and_compcor(tmp_path):
    tsv = _confounds(tmp_path / "sub-01_task-x_desc-confounds_timeseries.tsv")
    m, _ = ck.confounds_motion_metrics(tsv)
    assert m["n_trs"] == 30 and 0 < m["mean_fd"] < 0.2 and m["frac_fd_over_0p5"] == 0.0
    assert m["max_abs_trans_mm"] < 1.5 and m["max_abs_rot_deg"] < 1.5
    assert ck.verdict_for(m, norms_for("hmc_framewise_displacement"))[0] == "ok"
    assert ck.verdict_for(m, norms_for("hmc_rigid_body"))[0] == "ok"
    bad = _confounds(tmp_path / "sub-01_task-y_desc-confounds_timeseries.tsv", fd_scale=1.0, trans_mm=6.0)
    mb, _ = ck.confounds_motion_metrics(bad)
    assert ck.verdict_for(mb, norms_for("hmc_framewise_displacement"))[0] == "bad"
    assert ck.verdict_for(mb, norms_for("hmc_rigid_body"))[0] == "bad"

    c, _ = ck.compcor_components_metrics(tsv)
    assert c["n_acompcor"] == 2 and c["n_tcompcor"] == 1 and c["n_nan_inf_components"] == 0 and c["n_constant_components"] == 0
    assert c["acompcor_cumulative_variance"] == 0.52 and c["acompcor_masks"] == ["combined"]
    assert ck.verdict_for(c, norms_for("compcor_components_valid"))[0] == "ok"
    assert ck.verdict_for(c, norms_for("compcor_variance_explained"))[0] == "ok"


def test_fieldmap_and_delta_te(tmp_path):
    rng = np.random.default_rng(2)
    fm = tmp_path / "sub-01_fmapid-auto00000_desc-preproc_fieldmap.nii.gz"
    nib.save(nib.Nifti1Image(rng.normal(0, 40, (6, 6, 6)).astype("float32"), np.eye(4)), str(fm))
    m, _ = ck.fieldmap_stats_metrics(fm)
    assert m["finite_fraction"] == 1.0 and m["std_hz"] > 0 and m["p99_abs_hz"] < 300
    assert ck.verdict_for(m, norms_for("sdc_fieldmap_range"))[0] == "ok"
    flat = tmp_path / "flat_fieldmap.nii.gz"
    nib.save(nib.Nifti1Image(np.full((6, 6, 6), 3.0, dtype="float32"), np.eye(4)), str(flat))
    assert ck.verdict_for(ck.fieldmap_stats_metrics(flat)[0], norms_for("sdc_fieldmap_range"))[0] == "bad"

    js = tmp_path / "sub-01_phasediff.json"
    js.write_text(json.dumps({"EchoTime1": 0.00492, "EchoTime2": 0.00738}))
    d, _ = ck.phasediff_delta_te_metrics(js)
    assert d["has_both_echoes"] and d["echoes_ordered"] and abs(d["delta_te_ms"] - 2.46) < 1e-6
    assert ck.verdict_for(d, norms_for("sdc_delta_te"))[0] == "ok"
    js.write_text(json.dumps({"EchoTime1": 0.00492, "EchoTime2": 0.01292}))   # 8 ms
    assert ck.verdict_for(ck.phasediff_delta_te_metrics(js)[0], norms_for("sdc_delta_te"))[0] == "bad"


def test_glob_templates_give_one_record_per_run(tmp_path):
    deriv = tmp_path / "deriv"
    (deriv / "sub-01" / "ses-01" / "func").mkdir(parents=True)
    (deriv / "sub-01" / "ses-02" / "func").mkdir(parents=True)
    _bold(deriv / "sub-01" / "ses-01" / "func" / "sub-01_ses-01_task-a_desc-preproc_bold.nii.gz")
    _bold(deriv / "sub-01" / "ses-02" / "func" / "sub-01_ses-02_task-b_run-2_desc-preproc_bold.nii.gz", spike=True)
    ctx = {"derivatives_dir": str(deriv), "subject": "01"}
    tmpl = "{derivatives_dir}/sub-{subject}/**/func/*_desc-preproc_bold.nii.gz"
    found = ck.resolve_artifacts(tmpl, ctx)
    assert [ck.substep_label(p) for p in found] == ["ses-01_task-a", "ses-02_task-b_run-2"]
    assert ck.resolve_artifacts("{derivatives_dir}/nothing/*.nii.gz", ctx) == []

    checks = [c for c in FmriprepNode.CHECKS if c.step == "bold_spikes"]
    sink = ck.CheckpointSink(tmp_path / "cp.jsonl")
    w = ck.CheckpointWatcher(checks, ctx, sink, run_id="r", node="wf.fp", subject="01", poll_interval=0.01)
    produced = w.sweep(final=True)
    assert [cp.step for cp in produced] == ["bold_spikes[ses-01_task-a]", "bold_spikes[ses-02_task-b_run-2]"]
    assert produced[0].verdict == "ok" and produced[1].verdict == "suspicious"
    assert produced[1].expectations == {"n_zero_volumes": ["==", 0], "n_spike_volumes": ["<", 10]}   # norms keyed on the base step
    assert w.sweep(final=True) == []   # unchanged files are not re-evaluated


def test_fmriprep_checks_cover_the_constraint_tables_that_apply():
    steps = {c.step for c in FmriprepNode.CHECKS}
    assert {"bold_nan_inf", "bold_spikes", "hmc_framewise_displacement", "hmc_rigid_body", "sdc_fieldmap_range",
            "sdc_delta_te", "boldref_single_volume", "boldref_integrity", "compcor_components_valid", "compcor_variance_explained"} <= steps
    assert all(c.live for c in FmriprepNode.CHECKS), "a container app only sweeps live checks"
    ctx = FmriprepNode().checkpoint_context({"bids_dir": "/b", "subject": "sub-01", "output_dir": "/o"}, {}, Path("/n"))
    assert ctx["bids_dir"] == "/b" and ctx["subject"] == "01"


def test_mode_gates_structural_qc_and_the_freesurfer_checks():
    from fmriflow.preproc.node_registry import node_ui
    fs = set(FmriprepNode.FS_STEPS)
    for mode in ("func_only", "func_precomputed_anat"):
        assert node_ui(FmriprepNode, {"mode": mode})["structural_qc"] is None
        steps = {c.step for c in ck.resolve_checks(FmriprepNode, [], {"mode": mode})}
        assert not (steps & fs) and "bold_spikes" in steps
    assert node_ui(FmriprepNode, {"mode": "anat_only"})["structural_qc"] == "fs_subjects_dir"
    steps = {c.step for c in ck.resolve_checks(FmriprepNode, [], {"mode": "anat_only"})}
    assert fs <= steps and "bold_spikes" not in steps
    full = {c.step for c in ck.resolve_checks(FmriprepNode, [], {"mode": "full"})}
    assert fs <= full and "bold_spikes" in full
    # without params (the library listing) nothing is hidden
    assert node_ui(FmriprepNode)["structural_qc"] == "fs_subjects_dir"
