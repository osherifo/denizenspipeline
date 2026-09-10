"""Editable checkpoints: metric registry, norms overlay, pipeline-level checks, try-it route."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

nib = pytest.importorskip("nibabel")
nipype = pytest.importorskip("nipype")

from fmriflow.preproc import checkpoints as ck  # noqa: E402
from fmriflow.preproc import norms as nm  # noqa: E402
from fmriflow.preproc.graph import Pipeline, PipelineNode, PipelineRunRequest  # noqa: E402
from fmriflow.preproc.node_registry import NodeRegistry  # noqa: E402
from fmriflow.preproc.pipeline_runner import PipelineRunner  # noqa: E402
from fmriflow.server.services.run_registry import RunStateFile  # noqa: E402



@pytest.fixture(autouse=True)
def _all_checks(monkeypatch):
    """These tests exercise the whole check set; the product default keeps only a few live."""
    from fmriflow.preproc import norms as _norms
    monkeypatch.setattr(_norms, "ACTIVE_CHECKS", None)

def _nifti(path: Path, shape=(4, 4, 4, 6), value=100.0) -> Path:
    rng = np.random.default_rng(0)
    data = (value + rng.normal(0, 1, shape)).astype("float32")   # a little noise so tSNR is finite
    data[0, 0, 0] = 0
    nib.save(nib.Nifti1Image(data, np.eye(4)), str(path))
    return path


def test_metric_registry_and_check_roundtrip(tmp_path):
    names = {m["name"] for m in ck.metric_catalog()}
    assert {"volume_intensity", "surface", "thickness", "aseg_stats", "output_file", "nifti_stats"} <= names
    c = ck.Check.from_dict({"step": "my", "artifact": "{node_dir}/x.nii.gz", "metric": "nifti_stats",
                            "norms": {"hard": {"nonzero_fraction": [">", 0.5]}, "soft": {"n_trs": [">=", 3]}}})
    assert c.metrics is ck.nifti_stats_metrics and c.source == "pipeline"
    d = c.to_dict()
    assert d["metric"] == "nifti_stats" and d["norms"]["hard"]["nonzero_fraction"] == (">", 0.5)
    with pytest.raises(KeyError):
        ck.Check.from_dict({"step": "x", "artifact": "a", "metric": "no_such_metric"})
    with pytest.raises(ValueError):
        ck.Check.from_dict({"step": "x", "artifact": "a", "metric": "nifti_stats", "norms": {"hard": {"m": "not-a-bound"}}})

    m, _ = ck.nifti_stats_metrics(_nifti(tmp_path / "a.nii.gz"))
    assert m["is_4d"] and m["n_trs"] == 6 and 0.9 < m["nonzero_fraction"] < 1.0 and "tsnr_median" in m


def test_addon_metric_is_discovered(tmp_path):
    d = tmp_path / "checks"; d.mkdir()
    (d / "mine.py").write_text(
        "from fmriflow.preproc.checkpoints import checkpoint_metric\n"
        "@checkpoint_metric('always_seven')\n"
        "def seven(path):\n    return {'seven': 7}, {}\n")
    ck.load_addon_metrics([d])
    assert ck.get_metric("always_seven")(Path("/nowhere")) == ({"seven": 7}, {})


def test_resolve_checks_disable_rebound_and_add():
    class Node:
        CHECKS = [ck.Check(step="nu.mgz", artifact="{fs_subject_dir}/mri/nu.mgz", metrics=ck.volume_intensity_metrics),
                  ck.Check(step="T1.mgz", artifact="{fs_subject_dir}/mri/T1.mgz", metrics=ck.volume_intensity_metrics)]
    out = ck.resolve_checks(Node, [
        {"step": "T1.mgz", "enabled": False},
        {"step": "nu.mgz", "norms": {"hard": {"n_unique": [">", 10]}}},
        {"step": "mask", "artifact": "{node_dir}/mask.nii.gz", "metric": "nifti_stats"},
    ])
    by = {c.step: c for c in out}
    assert set(by) == {"nu.mgz", "mask"}
    assert by["nu.mgz"].metrics is ck.volume_intensity_metrics and by["nu.mgz"].norms == {"hard": {"n_unique": (">", 10)}} and by["nu.mgz"].source == "pipeline"
    assert by["mask"].metric == "nifti_stats" and by["mask"].source == "pipeline"


def test_user_norms_overlay_merges_and_saves(tmp_path, monkeypatch):
    monkeypatch.setenv("FMRIFLOW_HOME", str(tmp_path / "home"))
    nm._user_cache = None
    base = nm.norms_for("lh.thickness")
    assert base["soft"]["mean_mm"] == ("between", (2.2, 3.0))
    nm.save_user_norms({"lh.thickness": {"soft": {"mean_mm": ["between", [2.0, 3.2]]}}, "mystep": {"hard": {"p50": [">", 5]}}})
    assert nm.user_norms_path().is_file()
    got = nm.norms_for("lh.thickness")
    assert got["soft"]["mean_mm"] == ("between", (2.0, 3.2)) and got["hard"] == base["hard"]   # only that bound changed
    assert nm.norms_for("mystep") == {"hard": {"p50": (">", 5)}, "soft": {}}
    rows = {(r["step"], r["kind"], r["metric"]): r for r in nm.norms_table()}
    assert rows[("lh.thickness", "soft", "mean_mm")]["source"] == "user" and rows[("lh.thickness", "hard", "mean_mm")]["source"] == "builtin"
    assert rows[("lh.thickness", "soft", "mean_mm")]["builtin"] == ["between", [2.2, 3.0]]
    nm.save_user_norms({})
    assert not nm.user_norms_path().exists() and nm.norms_for("lh.thickness")["soft"]["mean_mm"] == ("between", (2.2, 3.0))
    with pytest.raises(ValueError):
        nm.save_user_norms({"x": {"hard": {"m": "nope"}}})


def test_pipeline_level_check_runs_on_an_interface_node(tmp_path, monkeypatch):
    """A check written on the pipeline node is evaluated on completion against its output."""
    monkeypatch.setenv("FMRIFLOW_HOME", str(tmp_path / "home"))
    deriv = tmp_path / "deriv" / "sub-01" / "func"; deriv.mkdir(parents=True)
    _nifti(deriv / "sub-01_task-x_run-1_desc-preproc_bold.nii.gz")
    (deriv / "sub-01_task-x_run-1_desc-confounds_timeseries.tsv").write_text("trans_x\n" + "0.1\n" * 6)
    registry = NodeRegistry(include_parked=True, user_dirs=[]).discover()
    pipeline = Pipeline(name="p", inputs={"derivatives_dir": {"kind": "dir"}, "subject": {"kind": "str"}}, nodes=[
        PipelineNode(id="source", type="derivatives_source", kind="source", bindings={"derivatives_dir": "$inputs.derivatives_dir", "subject": "$inputs.subject"}),
        PipelineNode(id="smooth", type="smooth", kind="interface", params={"fwhm": 2.0}, iter={"handle": "in_file"},
                     checks=[{"step": "smoothed_ok", "artifact": "{out_file}", "metric": "nifti_stats",
                              "norms": {"hard": {"n_trs": [">", 100]}}}]),
    ], edges=[], manifest={"backend_node": "source", "bold_from": "smooth.out_file"})
    from fmriflow.preproc.graph import PipelineEdge
    pipeline.edges = [PipelineEdge(id="e", source="source", target="smooth", source_handle="bold", target_handle="in_file")]
    cps = tmp_path / "checkpoints.jsonl"
    result = PipelineRunner(registry, run_id="r", checkpoints_path=cps).run(
        pipeline, PipelineRunRequest(subject="01", output_dir=str(tmp_path / "out"), derivatives_dir=str(tmp_path / "deriv")))
    assert result.status == "completed", result.errors
    records = [json.loads(l) for l in cps.read_text().splitlines()]
    mine = [r for r in records if r["step"] == "smoothed_ok"]
    assert mine and mine[0]["verdict"] == "bad" and "n_trs=6 violates > 100" in mine[0]["reasons"][0]


def test_checks_routes(tmp_path, monkeypatch):
    monkeypatch.setenv("FMRIFLOW_INCLUDE_PARKED_NODES", "1")
    monkeypatch.setenv("FMRIFLOW_HOME", str(tmp_path / "home"))
    nm._user_cache = None
    from fmriflow.server.app import create_app
    app = create_app(derivatives_dir=str(tmp_path / "derivatives"))
    c = TestClient(app)
    assert "nifti_stats" in {m["name"] for m in c.get("/api/preproc/checks/metrics").json()["metrics"]}
    fp = c.get("/api/preproc/nodes/fmriprep/checks").json()["checks"]
    assert any(x["step"] == "nu.mgz" and x["metric"] == "volume_intensity" for x in fp)

    r = c.put("/api/preproc/checks/norms", json={"norms": {"wm.mgz": {"hard": {"wm_volume_cm3": ["between", [200, 1000]]}}}})
    assert r.status_code == 200
    rows = {(x["step"], x["kind"], x["metric"]): x for x in c.get("/api/preproc/checks/norms").json()["rows"]}
    assert rows[("wm.mgz", "hard", "wm_volume_cm3")]["source"] == "user" and rows[("wm.mgz", "hard", "wm_volume_cm3")]["value"] == [200, 1000]
    assert c.put("/api/preproc/checks/norms", json={"norms": {"x": {"hard": {"m": "bad"}}}}).status_code == 400

    # try-it against a run's node output
    work = tmp_path / "work" / "p__sub_01" / "sm"; work.mkdir(parents=True)
    out = _nifti(work / "out.nii.gz")
    mgr = app.state.preproc_run_manager
    state = RunStateFile(run_id="r1", kind="preproc", backend="pipeline", subject="01", status="done",
                         params={"pipeline": "p", "workflow": "p__sub_01", "work_dir": str(tmp_path / "work"), "nodes": [{"id": "sm", "type": "smooth", "kind": "interface"}], "n_nodes": 1},
                         result={"status": "completed", "duration_s": 1, "errors": [], "nodes": [{"node_id": "sm", "node_type": "smooth", "kind": "interface", "status": "ok", "duration_s": 1, "work_dir": str(work), "outputs": {"out_file": str(out)}, "error": None}]})
    mgr.registry.register(state); mgr.registry.update(state)
    body = {"run_id": "r1", "node_id": "sm", "check": {"step": "t", "artifact": "{out_file}", "metric": "nifti_stats", "norms": {"soft": {"n_trs": [">", 10]}}}}
    r = c.post("/api/preproc/checks/evaluate", json=body).json()
    assert r["exists"] and r["checkpoint"]["verdict"] == "suspicious" and r["checkpoint"]["metrics"]["n_trs"] == 6
    body["check"]["artifact"] = "{node_dir}/missing.nii.gz"
    assert c.post("/api/preproc/checks/evaluate", json=body).json()["exists"] is False
    body["check"]["artifact"] = "{nope}/x"
    assert c.post("/api/preproc/checks/evaluate", json=body).status_code == 400
    body["check"] = {"step": "t", "artifact": "{out_file}", "metric": "does_not_exist"}
    assert c.post("/api/preproc/checks/evaluate", json=body).status_code == 400


# ── user metrics: CRUD from the UI ──────────────────────────────────


GOOD = """
from pathlib import Path
from fmriflow.preproc.checkpoints import checkpoint_metric


@checkpoint_metric("file_size")
def file_size(path: Path):
    \"\"\"Size of the file in bytes.\"\"\"
    return {"size_bytes": Path(path).stat().st_size}, {"name": Path(path).name}
"""


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("FMRIFLOW_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("FMRIFLOW_INCLUDE_PARKED_NODES", "1")     # these routes run smooth pipelines
    ck.load_addon_metrics(reload=True)
    yield tmp_path / "home"
    ck.load_addon_metrics(reload=True)


def test_user_metric_lifecycle(home, tmp_path):
    n_builtin = len(ck.metric_catalog())
    assert all(m["tier"] == "builtin" for m in ck.metric_catalog())

    path = ck.save_user_metric("file_size", GOOD)
    assert path == home / "addons" / "checks" / "file_size.py"
    rows = {m["name"]: m for m in ck.metric_catalog()}
    assert len(rows) == n_builtin + 1
    assert rows["file_size"]["tier"] == "user" and rows["file_size"]["path"] == str(path)
    assert rows["file_size"]["description"] == "Size of the file in bytes."
    assert ck.metric_source("file_size") == GOOD
    assert "def nifti_stats_metrics" in ck.metric_source("nifti_stats")

    f = tmp_path / "x.txt"; f.write_text("hello")
    r = ck.run_metric("file_size", f)
    assert r == {"ok": True, "metrics": {"size_bytes": 5}, "detail": {"name": "x.txt"}}
    assert ck.run_metric("file_size", tmp_path / "nope")["ok"] is False
    assert ck.Check.from_dict({"step": "s", "artifact": "{node_dir}/x", "metric": "file_size"}).metrics is ck.get_metric("file_size")

    # update in place: the new code replaces the old registration
    ck.save_user_metric("file_size", GOOD.replace('{"size_bytes": Path(path).stat().st_size}', '{"size_kb": Path(path).stat().st_size / 1024}'))
    assert "size_kb" in ck.run_metric("file_size", f)["metrics"]

    assert ck.delete_user_metric("file_size") == path and not path.exists()
    assert "file_size" not in {m["name"] for m in ck.metric_catalog()}
    with pytest.raises(KeyError):
        ck.delete_user_metric("file_size")


def test_user_metric_refusals(home):
    with pytest.raises(ValueError, match="built-in"):
        ck.save_user_metric("nifti_stats", GOOD)
    with pytest.raises(ValueError, match="built-in"):
        ck.delete_user_metric("nifti_stats")
    with pytest.raises(ValueError, match="letters"):
        ck.save_user_metric("bad name", GOOD)
    with pytest.raises(ValueError, match="syntax"):
        ck.save_user_metric("broken", "def (:")
    with pytest.raises(ValueError, match="fails to run"):
        ck.save_user_metric("boom", "raise RuntimeError('no')")
    with pytest.raises(ValueError, match=r"must register @checkpoint_metric\('other'\)"):
        ck.save_user_metric("other", GOOD)
    with pytest.raises(ValueError, match="override built-in"):
        ck.save_user_metric("mine", GOOD + "\n@checkpoint_metric('nifti_stats')\ndef m(p): return {}, {}\n@checkpoint_metric('mine')\ndef mm(p): return {}, {}\n")
    # a refused save registers nothing and writes nothing
    assert "nifti_stats" in {m["name"] for m in ck.metric_catalog() if m["tier"] == "builtin"}
    assert not (home / "addons" / "checks" / "mine.py").exists()


def test_broken_addon_file_is_reported_not_fatal(home):
    d = home / "addons" / "checks"; d.mkdir(parents=True, exist_ok=True)
    (d / "bad.py").write_text("import nothing_like_this\n")
    ck.load_addon_metrics(reload=True)
    row = next(m for m in ck.metric_catalog() if m["name"] == "bad")
    assert row["tier"] == "user" and "ModuleNotFoundError" in row["error"]
    assert "nothing_like_this" in ck.metric_source("bad")


def test_metric_routes(home, tmp_path):
    from fmriflow.server.app import create_app
    c = TestClient(create_app(derivatives_dir=str(tmp_path / "d")))
    assert "checkpoint_metric" in c.get("/api/preproc/checks/metrics/scaffold").json()["code"]
    assert c.get("/api/preproc/checks/metrics/nifti_stats").json()["builtin"] is True
    assert c.get("/api/preproc/checks/metrics/nope").status_code == 404

    r = c.put("/api/preproc/checks/metrics/file_size", json={"code": GOOD})
    assert r.status_code == 200 and r.json()["path"].endswith("addons/checks/file_size.py")
    assert {m["name"]: m["tier"] for m in r.json()["metrics"]}["file_size"] == "user"
    listing = c.get("/api/preproc/checks/metrics").json()
    assert listing["addons_dir"].endswith("addons/checks") and listing["hidden"] == 0    # this module runs with every check live
    assert {m["name"] for m in listing["metrics"]} >= {"file_size", "nifti_stats"}
    assert c.get("/api/preproc/checks/metrics/file_size").json()["source"] == GOOD
    assert c.put("/api/preproc/checks/metrics/nifti_stats", json={"code": GOOD}).status_code == 400
    assert c.put("/api/preproc/checks/metrics/x", json={"code": "def (:"}).status_code == 400

    f = tmp_path / "y.txt"; f.write_text("abc")
    r = c.post("/api/preproc/checks/metrics/file_size/run", json={"path": str(f)}).json()
    assert r["ok"] and r["metrics"] == {"size_bytes": 3}
    assert c.post("/api/preproc/checks/metrics/nope/run", json={"path": str(f)}).status_code == 404

    assert c.delete("/api/preproc/checks/metrics/nifti_stats").status_code == 403
    assert c.delete("/api/preproc/checks/metrics/file_size").json()["deleted"]
    assert c.delete("/api/preproc/checks/metrics/file_size").status_code == 404


def test_default_allow_list_keeps_three_checks_live(monkeypatch):
    """The product default: three bounds, hard only; everything else is parked."""
    from fmriflow.preproc import norms as _norms
    from fmriflow.preproc.nodes.fmriprep import FmriprepNode
    from fmriflow.preproc.nodes.smooth import SmoothNode as SmoothTransform
    monkeypatch.setattr(_norms, "ACTIVE_CHECKS", {"bold_output": ("is_4d", "n_trs"), "sdc_delta_te": ("has_both_echoes",)})
    rows = nm.norms_table()
    assert [(r["step"], r["metric"], r["kind"]) for r in rows] == [
        ("bold_output", "is_4d", "hard"), ("bold_output", "n_trs", "hard"), ("sdc_delta_te", "has_both_echoes", "hard")]
    assert nm.norms_for("bold_output") == {"hard": {"is_4d": ("==", True), "n_trs": (">", 1)}, "soft": {}}
    assert nm.norms_for("bold_spikes") == {"hard": {}, "soft": {}}
    assert [c.step for c in ck.resolve_checks(FmriprepNode, [], {"mode": "full"})] == ["sdc_delta_te"]
    assert [key for _, c in ck.generic_output_checks(SmoothTransform) for key in [c.key]] == ["bold_output"]
    # a pipeline-authored check on a parked step still runs, with its own bounds
    c = ck.Check.from_dict({"step": "bold_spikes", "artifact": "{node_dir}/x", "metric": "nifti_stats", "norms": {"hard": {"n_trs": [">", 1]}}})
    assert [x.step for x in ck.resolve_checks(SmoothTransform, [c.to_dict()], {})] == ["bold_spikes"]
    # the metric list follows: only the metrics behind the live checks (+ user metrics)
    reg = NodeRegistry(include_parked=True, user_dirs=[]).discover()
    assert ck.active_metric_names(reg) == {"output_file", "phasediff_delta_te"}


def test_parked_records_are_hidden_on_read_and_pruned_on_disk(tmp_path, monkeypatch):
    """Old runs recorded every check; with the allow-list they show (and keep) only the live ones."""
    from fmriflow.preproc import norms as _norms
    monkeypatch.setattr(_norms, "ACTIVE_CHECKS", {"bold_output": ("is_4d", "n_trs"), "sdc_delta_te": ("has_both_echoes",)})
    run = tmp_path / "run"; run.mkdir()
    recs = [
        {"stage": "preproc", "run_id": "r", "node": "w.fp", "step": "bold_nan_inf[task-x]", "subject": "01",
         "metrics": {"n_nan_inf": 0}, "expectations": {"n_nan_inf": ["==", 0]}, "soft_expectations": {}, "verdict": "ok", "t": 1},
        {"stage": "preproc", "run_id": "r", "node": "w.fp", "step": "nu.mgz", "subject": "01",
         "metrics": {"n_unique": 70}, "expectations": {"n_unique": [">", 100]}, "soft_expectations": {}, "verdict": "bad", "t": 1},
        {"stage": "preproc", "run_id": "r", "node": "w.sm", "step": "out_file", "subject": "01",              # bold_output
         "metrics": {"exists": True, "size_bytes": 9, "is_4d": True, "n_trs": 6, "nonzero_fraction": 0.5},
         "expectations": {"exists": ["==", True], "is_4d": ["==", True], "n_trs": [">", 1]},
         "soft_expectations": {"nonzero_fraction": [">", 0.01]}, "verdict": "suspicious", "reasons": ["nonzero_fraction=0.5 outside > 0.9"], "t": 1},
        {"stage": "preproc", "run_id": "r", "node": "w.fp", "step": "manifest", "subject": "01",              # generic `output`
         "metrics": {"exists": True, "size_bytes": 3}, "expectations": {"exists": ["==", True], "size_bytes": [">", 0]},
         "soft_expectations": {}, "verdict": "ok", "t": 1},
        {"stage": "preproc", "run_id": "r", "node": "w.sm", "step": "my_own", "subject": "01",               # pipeline-authored
         "metrics": {"mean": 3.0}, "expectations": {"mean": [">", 1]}, "soft_expectations": {}, "verdict": "ok", "t": 1},
    ]
    (run / "checkpoints.jsonl").write_text("\n".join(json.dumps(r) for r in recs) + "\n")
    events = [{"event": "started"}] + [{"event": "checkpoint", "node": r["node"], "step": r["step"], "verdict": r["verdict"],
                                        "reasons": r.get("reasons", []), "metrics": r["metrics"], "t": 1} for r in recs] + [{"event": "completed"}]
    (run / "events.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n")

    shown = ck.read_checkpoints(run / "checkpoints.jsonl")
    assert [c.step for c in shown] == ["out_file", "my_own"]
    assert shown[0].metrics == {"is_4d": True, "n_trs": 6} and shown[0].soft_expectations == {} and shown[0].verdict == "ok"
    assert len(ck.read_checkpoints(run / "checkpoints.jsonl", active_only=False)) == 5

    removed = ck.prune_parked(run)
    assert removed == {"checkpoints": 3, "events": 3}
    assert (run / "checkpoints.jsonl.parked").read_text().count("\n") == 5      # original kept
    kept = [json.loads(l) for l in (run / "checkpoints.jsonl").read_text().splitlines()]
    assert [k["step"] for k in kept] == ["out_file", "my_own"] and kept[0]["metrics"] == {"is_4d": True, "n_trs": 6}
    ev = [json.loads(l) for l in (run / "events.jsonl").read_text().splitlines()]
    assert [e.get("step", e["event"]) for e in ev] == ["started", "out_file", "my_own", "completed"]
    # a second prune changes nothing and keeps the first backup
    assert ck.prune_parked(run) == {"checkpoints": 0, "events": 0}
    assert (run / "checkpoints.jsonl.parked").read_text().count("\n") == 5


def test_metric_listing_hides_parked_builtins(home, tmp_path, monkeypatch):
    from fmriflow.preproc import norms as _norms
    from fmriflow.server.app import create_app
    monkeypatch.setattr(_norms, "ACTIVE_CHECKS", {"bold_output": ("is_4d", "n_trs"), "sdc_delta_te": ("has_both_echoes",)})
    ck.save_user_metric("file_size", GOOD)
    c = TestClient(create_app(derivatives_dir=str(tmp_path / "d")))
    r = c.get("/api/preproc/checks/metrics").json()
    assert {m["name"] for m in r["metrics"]} == {"output_file", "phasediff_delta_te", "file_size"}
    assert r["hidden"] > 5
    assert "nifti_stats" in {m["name"] for m in c.get("/api/preproc/checks/metrics?all=1").json()["metrics"]}
    # save / delete answer with the same filtered listing
    assert {m["name"] for m in c.put("/api/preproc/checks/metrics/file_size", json={"code": GOOD}).json()["metrics"]} == {"output_file", "phasediff_delta_te", "file_size"}
    assert {m["name"] for m in c.delete("/api/preproc/checks/metrics/file_size").json()["metrics"]} == {"output_file", "phasediff_delta_te"}

