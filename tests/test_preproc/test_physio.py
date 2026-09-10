"""Physio correction: .acq splitting, the PhLEM model, weight estimation / cleaning, and the nodes."""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import numpy as np
import pytest

nib = pytest.importorskip("nibabel")

from fmriflow.preproc.physio import acq as acq_mod
from fmriflow.preproc.physio.phlem import MODEL_TERMS, PhLEMData, build_regressors, peakdet
from fmriflow.preproc.physio.regress import (

    aligned_regressors, clean, estimate_weights, read_regressors, trim_bounds, write_regressors,
)


@pytest.fixture(autouse=True)
def _all_checks(monkeypatch):
    """These tests exercise the whole check set; the product default keeps only a few live."""
    from fmriflow.preproc import norms as _norms
    monkeypatch.setattr(_norms, "ACTIVE_CHECKS", None)

HZ = 100.0
TR = 2.0
N_TRS = (60, 45)          # two scan blocks
GAP_S = 30.0


# ── a synthetic BIOPAC recording ────────────────────────────────────


def _synthetic_channels(rng: np.random.Generator):
    """Four channels (PPG, unused, RESP, TTL) at HZ with two TTL blocks."""
    total_s = 5 + sum(n * TR for n in N_TRS) + GAP_S + 10
    n = int(total_s * HZ)
    t = np.arange(n) / HZ
    heart = 1.1 + 0.15 * np.sin(2 * np.pi * 0.05 * t)             # slowly varying heart rate (Hz)
    # a pulsatile, positive-going trace like a real pulse-ox: one sharp peak per beat
    ppg = 0.2 + np.clip(np.sin(2 * np.pi * np.cumsum(heart) / HZ), 0, None) ** 2 + 0.005 * rng.standard_normal(n)
    breath = 0.25 + 0.03 * np.sin(2 * np.pi * 0.02 * t)
    resp = np.sin(2 * np.pi * np.cumsum(breath) / HZ) + 0.05 * rng.standard_normal(n)
    ttl = np.ones(n) * 5.0
    start = 5.0
    for n_trs in N_TRS:
        for k in range(n_trs):
            i = int((start + k * TR) * HZ)
            ttl[i:i + 5] = 0.0                                     # a 50 ms low pulse per TR
        start += n_trs * TR + GAP_S
    return ppg, np.zeros(n), resp, ttl


class _Channel:
    def __init__(self, data):
        self.data = np.asarray(data, dtype=float)
        self.samples_per_second = HZ


class _Recording:
    def __init__(self, channels):
        self.channels = [_Channel(c) for c in channels]


@pytest.fixture
def acq_file(tmp_path, monkeypatch):
    """A fake ``bioread`` whose ``read_file`` returns the synthetic recording."""
    rng = np.random.default_rng(0)
    channels = _synthetic_channels(rng)
    fake = types.ModuleType("bioread")
    fake.read_file = lambda path: _Recording(channels)
    monkeypatch.setitem(sys.modules, "bioread", fake)
    path = tmp_path / "sub-01_physio.acq"
    path.write_bytes(b"fake")
    return path


# ── acq ─────────────────────────────────────────────────────────────


def test_split_acq_finds_two_blocks(acq_file):
    split = acq_mod.split_acq(acq_file)
    assert split.sampling_rate == HZ
    assert [b.n_pulses for b in split.blocks] == list(N_TRS)
    for b, n in zip(split.blocks, N_TRS):
        assert b.tr_s == pytest.approx(TR)
        assert b.summary()["n_trs"] == n
        assert b.data.shape == (4, int(n * TR * HZ))
    s = split.summary()
    assert s["n_blocks"] == 2 and s["channels"] == {"ppg": 0, "resp": 2, "ttl": 3}


def test_split_acq_validates_channels_and_pulses(acq_file):
    with pytest.raises(ValueError, match="ttl_channel=9"):
        acq_mod.split_acq(acq_file, ttl_channel=9)
    with pytest.raises(ValueError, match="no TTL pulses"):
        acq_mod.split_acq(acq_file, ttl_channel=1)      # the flat channel
    with pytest.raises(FileNotFoundError):
        acq_mod.split_acq(acq_file.with_name("nope.acq"))


# ── phlem ───────────────────────────────────────────────────────────


def test_peakdet_matches_reference():
    v = np.array([0, 1, 0, 2, 0, 3, 0], dtype=float)
    maxtab, mintab = peakdet(v, 0.5)
    assert maxtab[:, 0].tolist() == [1, 3, 5]
    assert mintab[:, 0].tolist() == [2, 4]
    with pytest.raises(ValueError):
        peakdet(v, 0)


def test_build_regressors_full_model(acq_file):
    blk = acq_mod.split_acq(acq_file).blocks[0]
    t, _, cardiac, resp = blk.data
    X, names = build_regressors(cardiac, resp, t, TR, HZ)
    assert X.shape == (N_TRS[0], 10)
    assert names == [
        "RETROICOR_PPG_phase1_sin", "RETROICOR_PPG_phase1_cos",
        "RETROICOR_PPG_phase2_sin", "RETROICOR_PPG_phase2_cos",
        "RETROICOR_RESP_phase1_sin", "RETROICOR_RESP_phase1_cos",
        "Rate_PPG", "Rate_RESP", "RespiratoryVariation", "HeartRateVariation",
    ]
    assert np.isfinite(X).all()
    # ~1.1 beats/s → ~2.2 beats per TR; ~0.25 breaths/s → ~0.5 per TR
    assert 1.5 < X[:, 6].mean() < 3.0
    assert 0.2 < X[:, 7].mean() < 0.9
    # phase terms are bounded
    assert np.abs(X[:, :6]).max() <= 1.0 + 1e-9


def test_build_regressors_subset_and_bad_term(acq_file):
    blk = acq_mod.split_acq(acq_file).blocks[1]
    t, _, cardiac, resp = blk.data
    X, names = build_regressors(cardiac, resp, t, TR, HZ, terms=["Rate"])
    assert X.shape == (N_TRS[1], 2) and names == ["Rate_PPG", "Rate_RESP"]
    ph = PhLEMData({"PPG": {"data": cardiac, "hz": HZ}}, t, TR)
    ph.preprocess()
    with pytest.raises(ValueError, match="unknown model term"):
        ph.make_model(["Bogus"])
    with pytest.raises(ValueError, match="unknown data type"):
        PhLEMData({"ECG": {"data": cardiac, "hz": HZ}}, t, TR)


def test_flat_trace_reports_no_peaks():
    t = np.arange(0, 20, 1 / HZ)
    ph = PhLEMData({"PPG": {"data": np.zeros_like(t), "hz": HZ}}, t, TR)
    with pytest.raises(ValueError, match="could not find peaks"):
        ph.preprocess("PPG")


# ── regress ─────────────────────────────────────────────────────────


def test_trim_bounds():
    assert trim_bounds(60, 60, auto_trim=True) == (0, 60)
    assert trim_bounds(60, 63, auto_trim=True) == (0, 60)
    assert trim_bounds(60, 63, auto_trim=False, trim_begin=1, trim_end=2) == (1, 61)
    with pytest.raises(ValueError, match="surplus"):
        trim_bounds(60, 58, auto_trim=True)
    with pytest.raises(ValueError, match="leaves nothing"):
        trim_bounds(60, 10, auto_trim=False, trim_begin=5, trim_end=5)


def test_aligned_regressors_reports_mismatch():
    X = np.random.default_rng(1).standard_normal((63, 3))
    with pytest.raises(ValueError, match="63 physio TRs != 60 BOLD TRs"):
        aligned_regressors(X, 60, auto_trim=False)
    assert aligned_regressors(X, 60, auto_trim=True).shape == (60, 3)
    X[:, 0] = 1.0
    with pytest.raises(ValueError, match="column\\(s\\) \\[0\\] are constant"):
        aligned_regressors(X, 60, auto_trim=True)


def _synthetic_bold(tmp_path, X, rng):
    """A small BOLD whose voxels carry a known mix of the regressors plus noise."""
    n_trs, n_reg = X.shape
    shape = (5, 4, 3)
    W = rng.standard_normal((*shape, n_reg)) * 2.0
    Z = (X - X.mean(0)) / X.std(0)
    signal = np.einsum("tr,xyzr->xyzt", Z, W)
    data = 1000 + 20 * signal + 5 * rng.standard_normal((*shape, n_trs))
    data[0, 0, 0, :] = 500.0                                     # a constant voxel (outside the head)
    img = nib.Nifti1Image(data.astype(np.float32), np.eye(4))
    img.header.set_zooms((3.0, 3.0, 3.0, TR))
    bold = tmp_path / "sub-01_task-x_bold.nii.gz"
    img.to_filename(str(bold))
    return bold


def test_estimate_then_clean_removes_the_physio_component(tmp_path):
    rng = np.random.default_rng(2)
    X = rng.standard_normal((40, 3))
    reg = write_regressors(tmp_path / "reg.tsv", X, ["a", "b", "c"])
    X2, names = read_regressors(reg)
    assert names == ["a", "b", "c"] and np.allclose(X2, X, atol=1e-6)

    bold = _synthetic_bold(tmp_path, X, rng)
    w = tmp_path / "w.nii.gz"
    info = estimate_weights(bold, reg, w)
    assert info["n_regressors"] == 3 and info["n_nan_inf"] == 0
    assert nib.load(str(w)).shape == (5, 4, 3, 3)

    out = tmp_path / "clean.nii.gz"
    s = clean(bold, reg, w, out)
    assert s["n_nan_inf"] == 0
    assert s["variance_removed_fraction"] > 0.8                  # the injected component dominates
    arr = np.asarray(nib.load(str(out)).dataobj)
    assert arr.dtype == np.float32
    assert np.allclose(arr[0, 0, 0, :], 500.0)                   # constant voxel keeps its mean, no NaN
    # cleaned voxels keep their mean and have unit variance around it
    v = arr[2, 2, 1, :]
    assert abs(v.mean() - np.asarray(nib.load(str(bold)).dataobj)[2, 2, 1, :].mean()) < 1e-2
    assert abs(v.std() - 1.0) < 1e-3


def test_clean_rejects_mismatched_weights(tmp_path):
    rng = np.random.default_rng(3)
    X = rng.standard_normal((40, 3))
    reg = write_regressors(tmp_path / "reg.tsv", X, ["a", "b", "c"])
    bold = _synthetic_bold(tmp_path, X, rng)
    bad = tmp_path / "bad.nii.gz"
    nib.Nifti1Image(np.zeros((5, 4, 3, 2), dtype=np.float32), np.eye(4)).to_filename(str(bad))
    with pytest.raises(ValueError, match="do not match"):
        clean(bold, reg, bad, tmp_path / "o.nii.gz")


# ── nodes ───────────────────────────────────────────────────────────


@pytest.fixture
def registry():
    from fmriflow.preproc.node_registry import NodeRegistry
    return NodeRegistry(include_parked=True, user_dirs=[]).discover()


def test_nodes_registered_with_checks(registry):
    reg = registry.info("physio_regressors")
    assert reg.kind == "interface" and reg.required_python == ["bioread"]
    assert reg.checks == ["physio_blocks", "physio_regressors"] and reg.ui["checkpoints"]
    assert "block" in reg.params_schema and reg.params_schema["model"]["enum"] == list(MODEL_TERMS)
    assert registry.info("physio_estimate").checks == ["physio_weights"]
    assert registry.info("physio_clean").checks == ["physio_clean"]
    assert registry.info("physio_clean").inputs["weights_file"]["required"] is False


def test_regressors_node_end_to_end(acq_file, tmp_path, registry):
    from fmriflow.preproc.nodes.physio import BLOCKS_NAME, REGRESSORS_NAME, physio_blocks_metrics, physio_regressors_metrics

    rng = np.random.default_rng(4)
    bold = _synthetic_bold(tmp_path, rng.standard_normal((N_TRS[1] - 2, 2)), rng)   # 43 TRs: block 1 has 45
    node = registry.get("physio_regressors")
    out_dir = tmp_path / "node"
    res = node.run({"physio_file": str(acq_file), "in_file": str(bold), "block": "1"}, out_dir, {"tr": 0, "block": 0})
    assert res["regressors_file"] == out_dir / REGRESSORS_NAME and res["blocks_file"] == out_dir / BLOCKS_NAME

    X, names = read_regressors(res["regressors_file"])
    assert X.shape == (N_TRS[1], 10)                                  # the input port beat the param
    summary = json.loads(res["blocks_file"].read_text())
    assert summary["selected"]["index"] == 1 and summary["tr_s"] == TR and summary["bold_n_trs"] == N_TRS[1] - 2

    m, detail = physio_blocks_metrics(res["blocks_file"])
    assert m["n_blocks"] == 2 and m["selected_block"] == 1 and m["tr_surplus"] == 2
    m, detail = physio_regressors_metrics(res["regressors_file"])
    assert m["n_trs"] == N_TRS[1] and m["n_regressors"] == 10 and m["n_nan_inf"] == 0 and m["n_constant_columns"] == 0
    assert detail["regressor_names"] == names


def test_regressors_node_errors(acq_file, tmp_path, registry):
    node = registry.get("physio_regressors")
    with pytest.raises(ValueError, match="set 'tr'"):
        node.run({"physio_file": str(acq_file)}, tmp_path / "a", {"tr": 0})
    with pytest.raises(ValueError, match=r"block 7 requested but .* has 2 block\(s\): #0 120s/60 TRs, #1 90s/45 TRs"):
        node.run({"physio_file": str(acq_file)}, tmp_path / "b", {"tr": 2000.0, "block": 7})   # ms accepted


def test_clean_node_estimates_when_no_weights(tmp_path, registry):
    from fmriflow.preproc.nodes.physio import CLEAN_SUMMARY_NAME, WEIGHTS_NAME, physio_clean_metrics

    rng = np.random.default_rng(5)
    X = rng.standard_normal((40, 3))
    reg = write_regressors(tmp_path / "reg.tsv", X, ["a", "b", "c"])
    bold = _synthetic_bold(tmp_path, X, rng)

    est = registry.get("physio_estimate")
    w = est.run({"in_file": str(bold), "regressors_file": str(reg)}, tmp_path / "est", {})["weights_file"]
    assert w.name == WEIGHTS_NAME and w.exists()

    cl = registry.get("physio_clean")
    out_dir = tmp_path / "clean"
    res = cl.run({"in_file": str(bold), "regressors_file": str(reg)}, out_dir, {"auto_trim": True})
    assert res["out_file"].name == "sub-01_task-x_bold_desc-physioclean_bold.nii.gz"
    assert res["weights_file"] == out_dir / WEIGHTS_NAME
    m, _ = physio_clean_metrics(out_dir / CLEAN_SUMMARY_NAME)
    assert m["n_nan_inf"] == 0 and m["variance_removed_fraction"] > 0.8

    # connected weights are reused, not re-estimated
    res2 = cl.run({"in_file": str(bold), "regressors_file": str(reg), "weights_file": str(w)}, tmp_path / "clean2", {})
    assert res2["weights_file"] == w


def test_norms_cover_the_physio_steps():
    from fmriflow.preproc.norms import norms_for
    for step in ("physio_blocks", "physio_regressors", "physio_weights", "physio_clean"):
        hard, soft = norms_for(step)
        assert hard or soft, step


# ── through the pipeline runner ─────────────────────────────────────


def test_physio_chain_runs_as_a_pipeline(acq_file, tmp_path, registry):
    """derivatives_source → physio_regressors (whole BOLD list, run i ↔ block i) → physio_clean ×N, with checkpoints."""
    from fmriflow.preproc.graph import Pipeline, PipelineRunRequest
    from fmriflow.preproc.pipeline_runner import PipelineRunner

    rng = np.random.default_rng(6)
    d = tmp_path / "deriv" / "sub-01" / "func"
    d.mkdir(parents=True)
    for r, n in zip((1, 2), N_TRS):
        img = nib.Nifti1Image((1000 + 10 * rng.standard_normal((4, 4, 3, n))).astype("float32"), np.eye(4))
        img.header.set_zooms((3.0, 3.0, 3.0, TR))
        img.to_filename(str(d / f"sub-01_task-x_run-{r}_desc-preproc_bold.nii.gz"))

    pipeline = Pipeline.from_dict({
        "schema_version": 1, "name": "physio_chain",
        "inputs": {"derivatives_dir": {"kind": "dir"}, "subject": {"kind": "str"}},
        "nodes": [
            {"id": "source", "type": "derivatives_source", "kind": "source",
             "data": {"params": {}, "bindings": {"derivatives_dir": "$inputs.derivatives_dir", "subject": "$inputs.subject"}},
             "position": {"x": 0, "y": 0}},
            {"id": "physio", "type": "physio_regressors", "kind": "interface",
             "data": {"params": {"tr": 0}, "literal_inputs": {"physio_file": str(acq_file)}},
             "position": {"x": 300, "y": 0}},
            {"id": "clean", "type": "physio_clean", "kind": "interface",
             "data": {"params": {"auto_trim": True}, "iter": {"handles": ["in_file", "regressors_file"]}},
             "position": {"x": 600, "y": 0}},
        ],
        "edges": [
            {"id": "e1", "source": "source", "sourceHandle": "bold", "target": "physio", "targetHandle": "in_file"},
            {"id": "e2", "source": "physio", "sourceHandle": "bold_files", "target": "clean", "targetHandle": "in_file"},
            {"id": "e3", "source": "physio", "sourceHandle": "regressors_file", "target": "clean", "targetHandle": "regressors_file"},
        ],
        "manifest": {"backend_node": "source", "bold_from": "clean.out_file"},
    })
    assert pipeline.validate(registry) == []

    events: list[dict] = []
    runner = PipelineRunner(registry, run_id="physio1", event_sink=events.append,
                            events_path=tmp_path / "events.jsonl", checkpoints_path=tmp_path / "checkpoints.jsonl")
    req = PipelineRunRequest(subject="01", output_dir=str(tmp_path / "out"), derivatives_dir=str(tmp_path / "deriv"))
    result = runner.run(pipeline, req)
    assert result.status == "completed", result.errors
    assert {r.node_id: r.status for r in result.node_records} == {"source": "ok", "physio": "ok", "clean": "ok"}
    assert len(result.manifest.runs) == 2
    assert all("physioclean" in r.output_file for r in result.manifest.runs)

    cps = [json.loads(line) for line in (tmp_path / "checkpoints.jsonl").read_text().splitlines()]
    steps = {c["step"].split("[")[0] for c in cps}
    assert {"physio_blocks", "physio_regressors", "physio_clean"} <= steps
    # one record per run, labelled by the run's BIDS entities
    steps = sorted(c["step"] for c in cps if c["step"].startswith("physio_blocks"))
    assert steps == ["physio_blocks[task-x_run-1]", "physio_blocks[task-x_run-2]"]
    blocks = {c["step"]: c["metrics"] for c in cps if c["step"].startswith("physio_blocks")}
    assert [blocks[st]["selected_block"] for st in steps] == [0, 1]
    assert sorted(c["step"] for c in cps if c["step"].startswith("physio_clean")) == ["physio_clean[clean0]", "physio_clean[clean1]"]
    assert all(c["verdict"] in ("ok", "suspicious") for c in cps), [(c["step"], c["reasons"]) for c in cps if c["verdict"] == "bad"]


# ── pairing runs with recordings ────────────────────────────────────


def test_pair_runs_one_recording_and_per_session():
    from fmriflow.preproc.physio.pairing import pair_runs
    bolds = ["/d/sub-01_ses-01_task-a_run-1_bold.nii.gz", "/d/sub-01_ses-01_task-a_run-2_bold.nii.gz",
             "/d/sub-01_ses-02_task-a_run-1_bold.nii.gz"]
    one, skipped = pair_runs(bolds, ["/p/all.acq"])
    assert [(p.block, p.physio_file, p.order) for p in one] == [(0, "/p/all.acq", "given"), (1, "/p/all.acq", "given"), (2, "/p/all.acq", "given")]
    assert skipped == []

    # matched by ses- label regardless of the order the files were given in
    two, _ = pair_runs(bolds, ["/p/sub-01_ses-02_physio.acq", "/p/sub-01_ses-01_physio.acq"])
    assert [(p.block, Path(p.physio_file).name, p.session) for p in two] == [
        (0, "sub-01_ses-01_physio.acq", "01"), (1, "sub-01_ses-01_physio.acq", "01"), (0, "sub-01_ses-02_physio.acq", "02")]

    # no ses- in the recording names: sorted order
    by_order, _ = pair_runs(bolds, ["/p/b.acq", "/p/a.acq"])
    assert [Path(p.physio_file).name for p in by_order] == ["a.acq", "a.acq", "b.acq"]

    # scan order from a key: run-2 was acquired before run-1
    t = {bolds[0]: 200.0, bolds[1]: 100.0, bolds[2]: 50.0}
    ordered, _ = pair_runs(bolds, ["/p/all.acq"], order_key=lambda b: t[b])
    assert [(Path(p.bold).name[-17:-12], p.block, p.order) for p in ordered] == [("run-1", 2, "acquisition_time"), ("run-2", 1, "acquisition_time"), ("run-1", 0, "acquisition_time")]

    # explicit sessions: only those runs are covered, the rest reported as skipped
    only2, skipped = pair_runs(bolds, ["/p/x.acq"], sessions=["02"])
    assert [p.bold for p in only2] == [bolds[2]] and skipped == bolds[:2]

    explicit, _ = pair_runs(bolds, ["/p/all.acq"], blocks=[1, 2, 4])
    assert [p.block for p in explicit] == [1, 2, 4] and explicit[0].order == "explicit"
    with pytest.raises(ValueError, match="one per run"):
        pair_runs(bolds, ["/p/all.acq"], blocks=[1])
    with pytest.raises(ValueError, match="set 'sessions'"):
        pair_runs(bolds[:2], ["/p/a.acq", "/p/b.acq"])
    with pytest.raises(ValueError, match="no BOLD runs for session"):
        pair_runs(bolds, ["/p/a.acq"], sessions=["09"])


def _bold(tmp_path, name, n, rng, acq_time=None):
    img = nib.Nifti1Image((1000 + 10 * rng.standard_normal((4, 4, 3, n))).astype("float32"), np.eye(4))
    img.header.set_zooms((3.0, 3.0, 3.0, TR))
    f = tmp_path / name
    img.to_filename(str(f))
    if acq_time:
        f.with_name(name.replace(".nii.gz", ".json")).write_text(json.dumps({"AcquisitionTime": acq_time, "RepetitionTime": TR}))
    return str(f)


def test_regressors_node_pairs_a_bold_list(acq_file, tmp_path, registry):
    from fmriflow.preproc.nodes.physio import BLOCKS_NAME
    rng = np.random.default_rng(7)
    # alphabetical order (run-1, run-2) is the reverse of scan order here: run-2 has 60 TRs = block 0
    bolds = [_bold(tmp_path, "sub-01_task-x_run-1_desc-preproc_bold.nii.gz", N_TRS[1], rng, "17:30:5.5"),
             _bold(tmp_path, "sub-01_task-x_run-2_desc-preproc_bold.nii.gz", N_TRS[0], rng, "16:58:10")]
    node = registry.get("physio_regressors")
    out_dir = tmp_path / "node"
    res = node.run({"physio_file": str(acq_file), "in_file": bolds}, out_dir, {"tr": 0})
    assert [p.name for p in res["regressors_file"]] == [
        "physio_regressors_sub-01_task-x_run-1_desc-preproc_bold.tsv", "physio_regressors_sub-01_task-x_run-2_desc-preproc_bold.tsv"]
    assert [str(p) for p in res["bold_files"]] == bolds
    assert [read_regressors(p)[0].shape[0] for p in res["regressors_file"]] == [N_TRS[1], N_TRS[0]]
    summaries = [json.loads(p.read_text()) for p in res["blocks_file"]]
    assert [(d["selected"]["index"], d["order"]) for d in summaries] == [(1, "acquisition_time"), (0, "acquisition_time")]

    # without sidecars the given order is used, and the trigger/TR check catches the wrong pairing
    for b in bolds:
        Path(b.replace(".nii.gz", ".json")).unlink()
    with pytest.raises(ValueError, match=r"(?s)do not line up .*run-1.*block #0 has 60 triggers, BOLD has 45 TRs"):
        node.run({"physio_file": str(acq_file), "in_file": bolds}, tmp_path / "n2", {"tr": 0})
    # ... unless the mapping is explicit
    res = node.run({"physio_file": str(acq_file), "in_file": bolds}, tmp_path / "n3", {"tr": 0, "blocks": [1, 0]})
    assert [json.loads(p.read_text())["selected"]["index"] for p in res["blocks_file"]] == [1, 0]

    # three runs but the recording has two blocks: refused, with both sides listed
    with pytest.raises(ValueError, match=r"splits into 2 block\(s\) .* but 3 BOLD run\(s\) .* set 'blocks'"):
        node.run({"physio_file": str(acq_file), "in_file": bolds + [bolds[0]]}, tmp_path / "n4", {"tr": 0})


def test_regressors_node_sessions_and_bids_dir(acq_file, tmp_path, registry):
    """One recording for ses-01; ses-00 test scans are left out; scan order read from the raw BIDS sidecars."""
    rng = np.random.default_rng(8)
    raw = tmp_path / "bids" / "sub-01" / "ses-01" / "func"
    raw.mkdir(parents=True)
    (raw / "sub-01_ses-01_task-b_bold.json").write_text(json.dumps({"AcquisitionTime": "16:00:00"}))
    (raw / "sub-01_ses-01_task-a_bold.json").write_text(json.dumps({"AcquisitionTime": "16:30:00"}))
    deriv = tmp_path / "deriv"; deriv.mkdir()
    bolds = [_bold(deriv, "sub-01_ses-00_task-test_desc-preproc_bold.nii.gz", 20, rng),
             _bold(deriv, "sub-01_ses-01_task-a_space-T1w_desc-preproc_bold.nii.gz", N_TRS[1], rng),
             _bold(deriv, "sub-01_ses-01_task-b_space-T1w_desc-preproc_bold.nii.gz", N_TRS[0], rng)]
    node = registry.get("physio_regressors")
    res = node.run({"physio_file": [str(acq_file)], "in_file": bolds, "bids_dir": str(tmp_path / "bids")},
                   tmp_path / "node", {"tr": 0, "sessions": ["01"]})
    assert [Path(b).name[:22] for b in res["bold_files"]] == ["sub-01_ses-01_task-a_s", "sub-01_ses-01_task-b_s"]
    d = [json.loads(p.read_text()) for p in res["blocks_file"]]
    assert [(x["selected"]["index"], x["session"], x["order"]) for x in d] == [(1, "01", "acquisition_time"), (0, "01", "acquisition_time")]
    assert d[0]["skipped_runs"] == ["sub-01_ses-00_task-test_desc-preproc_bold.nii.gz"]


# ── the node popup's physio view ────────────────────────────────────


def test_physio_view_routes(acq_file, tmp_path, monkeypatch, registry):
    """Run both nodes for real, register a run around their dirs, read them back through the API with images."""
    from fastapi.testclient import TestClient
    from fmriflow.server.services.physio_views import scan_physio_node
    from fmriflow.server.services.run_registry import RunStateFile

    monkeypatch.setenv("FMRIFLOW_HOME", str(tmp_path / "home"))
    rng = np.random.default_rng(9)
    bolds = [_bold(tmp_path, "sub-01_task-x_run-1_desc-preproc_bold.nii.gz", N_TRS[0], rng, "16:00:00"),
             _bold(tmp_path, "sub-01_task-x_run-2_desc-preproc_bold.nii.gz", N_TRS[1], rng, "16:30:00")]
    wf = "p__sub_01"; work = tmp_path / "work"
    reg_dir = work / wf / "physio_regressors"; clean_dir = work / wf / "physio_clean"
    res = registry.get("physio_regressors").run({"physio_file": str(acq_file), "in_file": bolds}, reg_dir, {"tr": 0})
    for i, (b, r) in enumerate(zip(res["bold_files"], res["regressors_file"])):
        registry.get("physio_clean").run({"in_file": str(b), "regressors_file": str(r)}, clean_dir / "mapflow" / f"_physio_clean{i}", {"auto_trim": True})

    view = scan_physio_node(reg_dir)
    assert view["kind"] == "regressors" and [it["block"] for it in view["items"]] == [0, 1]
    assert view["items"][0]["triggers"] == N_TRS[0] and view["items"][0]["order"] == "acquisition_time"
    view = scan_physio_node(clean_dir)
    assert view["kind"] == "clean" and len(view["items"]) == 2 and all(it["has_image"] for it in view["items"])
    assert 0 <= view["items"][0]["variance_removed_p50"] <= 1

    from fmriflow.server.app import create_app
    app = create_app(derivatives_dir=str(tmp_path / "derivatives"))
    mgr = app.state.preproc_run_manager
    state = RunStateFile(
        run_id="run1", kind="preproc", backend="pipeline", subject="01", status="done",
        params={"pipeline": "p", "workflow": wf, "work_dir": str(work), "output_dir": str(tmp_path / "out"),
                "nodes": [{"id": "physio_regressors", "type": "physio_regressors", "kind": "interface"},
                          {"id": "physio_clean", "type": "physio_clean", "kind": "interface"}], "n_nodes": 2},
        result={"status": "completed", "duration_s": 1.0, "errors": [], "nodes": [
            {"node_id": "physio_regressors", "node_type": "physio_regressors", "kind": "interface", "status": "ok", "duration_s": 1.0, "work_dir": str(reg_dir), "error": None, "outputs": {}},
            {"node_id": "physio_clean", "node_type": "physio_clean", "kind": "interface", "status": "ok", "duration_s": 1.0, "work_dir": str(clean_dir), "error": None, "outputs": {}},
        ]},
    )
    mgr.registry.register(state); mgr.registry.update(state)
    c = TestClient(app)
    r = c.get("/api/preproc/runs/run1/nodes/physio_regressors/physio").json()
    assert r["kind"] == "regressors" and [it["run"] for it in r["items"]] == [Path(b).name for b in bolds]
    assert r["items"][0]["image_url"].endswith("/physio/0/image.png")
    png = c.get(r["items"][0]["image_url"])
    assert png.status_code == 200 and png.headers["content-type"] == "image/png" and png.content[:4] == b"\x89PNG"
    r = c.get("/api/preproc/runs/run1/nodes/physio_clean/physio").json()
    assert r["kind"] == "clean" and [it["n_trs"] for it in r["items"]] == list(N_TRS)
    assert c.get(r["items"][1]["image_url"]).headers["content-type"] == "image/png"
    assert c.get("/api/preproc/runs/run1/nodes/physio_clean/physio/9/image.png").status_code == 404
