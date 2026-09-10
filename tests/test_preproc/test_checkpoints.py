"""Checkpoints: metrics, verdicts, live evaluation inside a container app, generic output checks, routes."""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pytest

from tests.test_preproc.conftest import install_parked_nodes  # noqa: E402

nib = pytest.importorskip("nibabel")
nipype = pytest.importorskip("nipype")

from nibabel import MGHImage  # noqa: E402
from nibabel.freesurfer import write_geometry, write_morph_data  # noqa: E402

from fmriflow.preproc import checkpoints as ck  # noqa: E402
from fmriflow.preproc.graph import Pipeline, PipelineEdge, PipelineNode, PipelineRunRequest  # noqa: E402
from fmriflow.preproc.nipype_adapters import make_container_interface  # noqa: E402
from fmriflow.preproc.node_registry import NodeRegistry, preproc_node  # noqa: E402
from fmriflow.preproc.nodes._parked import PARKED_DIR  # noqa: E402
from fmriflow.preproc.norms import norms_for  # noqa: E402
from fmriflow.preproc.pipeline_runner import PipelineRunner  # noqa: E402


# ── synthetic artefacts ───────────────────────────────────────────


@pytest.fixture(autouse=True)
def _all_checks(monkeypatch):
    """These tests exercise the whole check set; the product default keeps only a few live."""
    from fmriflow.preproc import norms as _norms
    monkeypatch.setattr(_norms, "ACTIVE_CHECKS", None)

def _volume(path: Path, collapsed: bool) -> Path:
    rng = np.random.default_rng(0)
    if collapsed:
        arr = np.full((24, 24, 24), 110, dtype="float32")
        mask = rng.random(arr.shape) < 0.16
        arr[mask] = rng.integers(20, 255, size=int(mask.sum()))
    else:
        arr = rng.integers(20, 255, size=(24, 24, 24)).astype("float32")
    arr[:3] = 0
    nib.save(MGHImage(arr, np.eye(4)), path)
    return path


def _tetra(path: Path) -> Path:
    v = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype="float64")
    f = np.array([[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]], dtype="int32")
    write_geometry(str(path), v, f)
    return path


def test_volume_metrics_and_verdicts(tmp_path):
    good = ck.evaluate(ck.Check("nu.mgz", "x", ck.volume_intensity_metrics), _volume(tmp_path / "g.mgz", False),
                       run_id="r", node="fp", subject="01")
    bad = ck.evaluate(ck.Check("nu.mgz", "x", ck.volume_intensity_metrics), _volume(tmp_path / "b.mgz", True),
                      run_id="r", node="fp", subject="01")
    assert good.verdict == "ok" and good.metrics["n_unique"] > 200
    assert bad.verdict == "bad" and bad.metrics["modal_value"] == 110.0 and bad.metrics["modal_fraction"] > 0.8
    assert any("modal_fraction" in r for r in bad.reasons)
    assert "histogram" in bad.detail and bad.expectations["modal_fraction"] == ["<", 0.5]
    again = ck.Checkpoint.from_dict(bad.to_dict())
    assert again.verdict == "bad" and again.step == "nu.mgz"


def test_surface_thickness_and_aseg_metrics(tmp_path):
    m, _ = ck.surface_metrics(_tetra(tmp_path / "lh.white"))
    assert m == {"n_vertices": 4, "n_faces": 4, "euler": 2, "n_defects": 0}

    write_morph_data(str(tmp_path / "lh.thickness"), np.array([2.5, 2.4, 0.0, 2.6, 0.0], dtype="float32"))
    t, _ = ck.thickness_metrics(tmp_path / "lh.thickness")
    assert t["zero_fraction"] == pytest.approx(0.4) and t["mean_mm"] == pytest.approx(2.5)
    cp = ck.evaluate(ck.Check("lh.thickness", "x", ck.thickness_metrics), tmp_path / "lh.thickness",
                     run_id="r", node="fp", subject="01")
    assert cp.verdict == "bad"   # 40 % zero-thickness vertices

    stats = tmp_path / "aseg.stats"
    stats.write_text("# Measure EstimatedTotalIntraCranialVol, eTIV, Estimated Total Intracranial Volume, 1500000.0, mm^3\n"
                     "# Measure BrainSegVol, BrainSegVol, Brain Segmentation Volume, 1200000.0, mm^3\n")
    a, _ = ck.aseg_stats_metrics(stats)
    assert a == {"etiv_cm3": 1500.0, "brainseg_cm3": 1200.0}


def test_verdict_rules_and_sequence_norms():
    norms = {"hard": {"a": (">", 1)}, "soft": {"b": ("between", (0, 10))}}
    assert ck.verdict_for({"a": 2, "b": 5}, norms) == ("ok", [])
    v, r = ck.verdict_for({"a": 2, "b": 50}, norms)
    assert v == "suspicious" and "b=50" in r[0]
    v, r = ck.verdict_for({"a": 0, "b": 5}, norms)
    assert v == "bad"
    v, r = ck.verdict_for({"b": 5}, norms)
    assert v == "unknown"
    assert ck.worst_verdict(["ok", "suspicious", "unknown"]) == "suspicious"
    base = norms_for("nu.mgz")
    assert base["hard"]["modal_fraction"] == ("<", 0.5)
    assert norms_for("nu.mgz", "mprage") == base          # no override defined → base


def test_output_file_metrics(tmp_path):
    p = tmp_path / "b.nii.gz"
    nib.save(nib.Nifti1Image(np.ones((2, 2, 2, 5), dtype="float32"), np.eye(4)), p)
    m, _ = ck.output_file_metrics(p)
    assert m["exists"] and m["is_4d"] and m["n_trs"] == 5 and m["nonzero_fraction"] == 1.0
    assert ck.output_file_metrics(tmp_path / "missing.nii.gz")[0] == {"exists": False}


def test_sink_and_reader_mirror_into_events(tmp_path):
    sink = ck.CheckpointSink(tmp_path / "cp.jsonl", tmp_path / "events.jsonl")
    cp = ck.evaluate(ck.Check("nu.mgz", "x", ck.volume_intensity_metrics), _volume(tmp_path / "b.mgz", True),
                     run_id="r", node="wf.fp", subject="01")
    sink.write(cp)
    assert [c.step for c in ck.read_checkpoints(tmp_path / "cp.jsonl")] == ["nu.mgz"]
    ev = json.loads((tmp_path / "events.jsonl").read_text().splitlines()[0])
    assert ev["event"] == "checkpoint" and ev["verdict"] == "bad" and ev["leaf"] == "fp"


# ── live evaluation inside a container app ────────────────────────

def _fake_app(collapsed_src: Path, sleep_after: float, name: str):
    @preproc_node(name, kind="container_app")
    class FakeRecon:
        INNER_NIPYPE_LOG = False
        CHECKPOINT_POLL_S = 0.3
        INPUTS = {"subject": {"kind": "str"}}
        OUTPUTS = ["done"]
        CHECKS = [ck.Check(step="nu.mgz", artifact="{fs_subject_dir}/mri/nu.mgz", metrics=ck.volume_intensity_metrics)]

        def checkpoint_context(self, inputs, params, out_dir):
            return {"node_dir": str(out_dir), "subject": "01", "fs_subject_dir": str(out_dir / "fs" / "sub-01")}

        def build_command(self, inputs, params, out_dir):
            mri = out_dir / "fs" / "sub-01" / "mri"
            return f"mkdir -p {mri} && cp {collapsed_src} {mri}/nu.mgz && sleep {sleep_after}"

        def collect(self, inputs, params, out_dir):
            return {"done": "yes"}
    return FakeRecon


def test_live_checkpoint_is_written_while_the_app_runs(tmp_path):
    App = _fake_app(_volume(tmp_path / "collapsed.mgz", True), sleep_after=2.5, name="_fake_recon_live")
    iface = make_container_interface(App, subject="01", checkpoints_path=str(tmp_path / "cp.jsonl"),
                                     events_path=str(tmp_path / "events.jsonl"), node_path="wf.fp", run_id="r1")
    (tmp_path / "node").mkdir()
    t0 = time.time()
    res = iface.run(cwd=str(tmp_path / "node"))
    assert res.outputs.done == "yes"
    cps = ck.read_checkpoints(tmp_path / "cp.jsonl")
    assert len(cps) == 1 and cps[0].verdict == "bad" and cps[0].node == "wf.fp" and cps[0].run_id == "r1"
    # Written before the app finished, not after.
    assert cps[0].t < t0 + 2.5
    assert any(json.loads(l)["event"] == "checkpoint" for l in (tmp_path / "events.jsonl").read_text().splitlines())


def test_abort_on_bad_terminates_the_app(tmp_path):
    App = _fake_app(_volume(tmp_path / "collapsed.mgz", True), sleep_after=30, name="_fake_recon_abort")
    iface = make_container_interface(App, subject="01", checkpoints_path=str(tmp_path / "cp.jsonl"),
                                     node_path="wf.fp", abort_on_bad=True)
    (tmp_path / "node").mkdir()
    t0 = time.time()
    with pytest.raises(RuntimeError, match="aborted on a bad checkpoint"):
        iface.run(cwd=str(tmp_path / "node"))
    assert time.time() - t0 < 20


# ── runner: generic output checks + abort ─────────────────────────

@pytest.fixture(scope="module")
def registry():
    return NodeRegistry(user_dirs=[PARKED_DIR]).discover()


def _chain(tmp_path):
    src = tmp_path / "in.nii.gz"
    nib.save(nib.Nifti1Image(np.random.rand(3, 3, 3, 4).astype("float32"), np.eye(4)), src)
    return Pipeline(
        name="chk",
        nodes=[PipelineNode(id="ident", type="identity", literal_inputs={"in_file": str(src)}),
               PipelineNode(id="sm", type="smooth", params={"fwhm": 1.0})],
        edges=[PipelineEdge(id="e", source="ident", target="sm", source_handle="out_file", target_handle="in_file")],
        manifest={"backend_node": "ident", "bold_from": "sm.out_file"},
    )


def test_runner_writes_generic_output_checkpoints(registry, tmp_path):
    events: list[dict] = []
    runner = PipelineRunner(registry, run_id="r5", event_sink=events.append,
                            events_path=tmp_path / "events.jsonl", checkpoints_path=tmp_path / "cp.jsonl")
    result = runner.run(_chain(tmp_path), PipelineRunRequest(subject="01", output_dir=str(tmp_path / "o")))
    assert result.status == "completed", result.errors
    cps = ck.read_checkpoints(tmp_path / "cp.jsonl")
    assert {(c.node.rsplit(".", 1)[-1], c.step) for c in cps} == {("ident", "out_file"), ("sm", "out_file")}
    assert all(c.verdict == "ok" for c in cps)
    assert any(e["event"] == "checkpoint" for e in events) is False  # mirrored into the file, not the sink
    assert any(json.loads(l)["event"] == "checkpoint" for l in (tmp_path / "events.jsonl").read_text().splitlines())


def test_runner_abort_on_bad_output(registry, tmp_path):
    """A node whose output is a 3D file where a 4D BOLD is expected is 'bad'; abort stops the run."""
    nodes_dir = tmp_path / "nodes"
    nodes_dir.mkdir()
    (nodes_dir / "flat.py").write_text('''
from fmriflow.preproc.node_registry import preproc_node

@preproc_node("flat3d")
class Flat:
    INPUTS = ["in_file"]; OUTPUTS = {"out_file": {"kind": "nifti"}}
    def run(self, inputs, out_dir, params):
        import nibabel as nib, numpy as np
        p = out_dir / "flat.nii.gz"
        nib.save(nib.Nifti1Image(np.ones((2, 2, 2), dtype="float32"), np.eye(4)), p)
        return {"out_file": p}
''')
    reg = NodeRegistry(user_dirs=[PARKED_DIR, nodes_dir]).discover()
    src = tmp_path / "in.nii.gz"
    nib.save(nib.Nifti1Image(np.ones((2, 2, 2, 2), dtype="float32"), np.eye(4)), src)
    pipeline = Pipeline(name="ab", nodes=[PipelineNode(id="f", type="flat3d", literal_inputs={"in_file": str(src)})], manifest={})
    runner = PipelineRunner(reg, run_id="r6", checkpoints_path=tmp_path / "cp.jsonl")
    result = runner.run(pipeline, PipelineRunRequest(subject="01", output_dir=str(tmp_path / "o"), abort_on_bad=True))
    assert result.status == "failed" and any("bad output" in e for e in result.errors)
    cps = ck.read_checkpoints(tmp_path / "cp.jsonl")
    assert cps and cps[0].verdict == "bad" and any("is_4d" in r for r in cps[0].reasons)


def test_checkpoints_route_and_thumbnail(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setenv("FMRIFLOW_HOME", str(tmp_path / "home"))
    install_parked_nodes(tmp_path / "home")
    from fmriflow.server.app import create_app
    client = TestClient(create_app())
    src = tmp_path / "in.nii.gz"
    nib.save(nib.Nifti1Image(np.random.rand(3, 3, 3, 4).astype("float32"), np.eye(4)), src)
    pipeline = {"name": "http", "nodes": [{"id": "ident", "type": "identity", "data": {"literal_inputs": {"in_file": str(src)}}}],
                "manifest": {"backend_node": "ident"}}
    run_id = client.post("/api/preproc/pipelines/run", json={"pipeline": pipeline, "subject": "01", "output_dir": str(tmp_path / "out")}).json()["run_id"]
    for _ in range(120):
        s = client.get(f"/api/preproc/runs/{run_id}").json()
        if s["status"] != "running":
            break
        time.sleep(0.5)
    assert s["status"] == "done" and s["checkpoints"]["n"] == 1 and s["checkpoints"]["worst"] == "ok"
    body = client.get(f"/api/preproc/runs/{run_id}/checkpoints").json()
    assert body["checkpoints"][0]["step"] == "out_file"
    png = client.get(f"/api/preproc/runs/{run_id}/checkpoints/0/thumbnail")
    assert png.status_code == 200 and png.headers["content-type"] == "image/png"
    assert client.get(f"/api/preproc/runs/{run_id}/checkpoints/9/thumbnail").status_code == 404


def test_checkpoint_watcher_stops_and_joins():
    """Regression: an attribute named `_stop` on a Thread subclass shadows
    Thread._stop() and makes join() raise "'Event' object is not callable"."""
    import threading
    from fmriflow.preproc.checkpoints import CheckpointWatcher
    w = CheckpointWatcher([], {}, lambda cp: None, run_id="r", node="n", subject="01", poll_interval=0.05)
    assert not isinstance(getattr(w, "_stop", None), threading.Event)
    w.start()
    w.stop()
    w.join(timeout=5)
    assert not w.is_alive()
