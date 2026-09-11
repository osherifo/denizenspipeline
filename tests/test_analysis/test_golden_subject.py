"""Subject runs, checked against golden records.

The graph engine replaced the stage orchestrator after matching it, on each config
below, in context values, artifacts, run summary (stages and per-node records),
events and files. Those orchestrator runs are kept as records in ``golden/`` (see
``_golden.py``). Utility nodes exist only in graph runs and are left out;
preparation-step records compare on id, kind, name and status because the graph
engine times each step for real.
"""

from __future__ import annotations

import copy
import json
import pickle
from pathlib import Path

import pytest

from fmriflow.analysis.catalog import NodeCatalog
from fmriflow.analysis.executor import GraphExecutor, run_subject_config
from fmriflow.exceptions import ConfigError, PipelineError, StageError
from fmriflow.modules import _decorators as deco
from fmriflow.orchestrator import PipelineOrchestrator
from fmriflow.pipeline import Pipeline
from fmriflow.registry import ModuleRegistry
from tests.test_analysis._golden import GOLDEN_DIR, check_golden, digest
from tests.test_integration.test_pipeline import _make_config, _make_registry


class _MeanScores:
    name = "zz_parity_mean"

    def analyze(self, context, config):
        result = context.get("result")
        context.put("analysis.mean_score", float(result.scores.mean()))
        context.put("analysis.scores_x2", result.scores * 2)

    def validate_config(self, config):
        return []


class _BoomAnalyzer(_MeanScores):
    name = "zz_parity_boom"

    def analyze(self, context, config):
        raise RuntimeError("analyzer boom")


class _SummaryReporter:
    name = "zz_parity_summary"

    def report(self, result, context, config):
        out = Path(config["reporting"]["output_dir"])
        out.mkdir(parents=True, exist_ok=True)
        path = out / "summary.json"
        mean = context.get("analysis.mean_score") if context.has("analysis.mean_score") else None
        path.write_text(json.dumps({"mean": mean, "n": int(result.n_voxels)}))
        return {"summary": str(path)}

    def validate_config(self, config):
        return []


class _FailReporter(_SummaryReporter):
    name = "zz_parity_fail_reporter"

    def report(self, result, context, config):
        raise RuntimeError("reporter boom")


class _FailModel:
    name = "zz_parity_fail_model"

    def fit(self, data, config):
        raise RuntimeError("model boom")

    def validate_config(self, config):
        return []


class _ParityQa:
    def report(self, value, config, out_dir):
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "qa.txt"
        path.write_text(type(value).__name__)
        return {"qa": str(path)}


@pytest.fixture(autouse=True)
def parity_modules():
    deco._analyzers["zz_parity_mean"] = _MeanScores
    deco._analyzers["zz_parity_boom"] = _BoomAnalyzer
    deco._reporters["zz_parity_summary"] = _SummaryReporter
    deco._reporters["zz_parity_fail_reporter"] = _FailReporter
    deco._models["zz_parity_fail_model"] = _FailModel
    deco._qa_reporters.setdefault("model", {})["zz_parity_qa"] = _ParityQa
    yield
    for registry, name in ((deco._analyzers, "zz_parity_mean"), (deco._analyzers, "zz_parity_boom"),
                           (deco._reporters, "zz_parity_summary"), (deco._reporters, "zz_parity_fail_reporter"),
                           (deco._models, "zz_parity_fail_model"), (deco._qa_reporters["model"], "zz_parity_qa")):
        registry.pop(name, None)


def _run(config, tmp_path, monkeypatch):
    cfg = copy.deepcopy(config)
    out = tmp_path / "run"
    cfg["reporting"]["output_dir"] = str(out)
    events = tmp_path / "events.jsonl"
    monkeypatch.setenv("FMRIFLOW_EVENTS_FILE", str(events))
    registry = _make_registry()
    error = None
    executor = GraphExecutor(NodeCatalog(registry).discover())
    try:
        run_subject_config(cfg, registry, executor=executor)
    except Exception as exc:
        error = exc
    ctx = executor.last_context
    lines = events.read_text().splitlines() if events.exists() else []
    return ctx, error, [json.loads(line) for line in lines], out


def _node(n):
    base = (n.id, n.kind, n.name, n.status)
    if n.kind == "preparation_step":
        return base
    return base + (n.detail, tuple(n.outputs), tuple(n.qa_outputs))


def _summary(ctx):
    return [(s.name, s.status, s.detail, [_node(n) for n in s.nodes if n.kind != "utility"])
            for s in ctx.run_summary.stages]


def _events(events):
    return [(e["event"], e.get("stage") or e.get("node_id"), e.get("detail"))
            for e in events if e.get("kind") != "utility"]


def _files(out):
    if not out.exists():
        return []
    return sorted(str(p.relative_to(out)) for p in out.rglob("*") if p.is_file() and p.name != "graph.json")


def _check(name, config, tmp_path, monkeypatch, extra=None):
    ctx, err, events, out = _run(config, tmp_path, monkeypatch)
    # guard against vacuous passes: the run really happened and emitted events
    assert _events(events) and _summary(ctx)
    assert any(e.get("kind") == "utility" for e in events)
    root = str(out)
    record = {
        "error": None if err is None else [type(err).__name__, str(err)],
        "summary": _summary(ctx),
        "events": _events(events),
        "context": {key: digest(ctx._store[key], root) for key in sorted(ctx._store)},
        "artifacts": {k: {n: str(Path(p).relative_to(out)) if str(p).startswith(root) else p for n, p in v.items()}
                      for k, v in ctx.artifacts.items()},
        "files": _files(out),
    }
    if extra is not None:
        record.update(extra(out))
    check_golden(f"subject_{name}", record)
    return ctx, err, out


def test_full_run_with_analyzers_reporters_intermediates_and_qa(tmp_path, monkeypatch):
    cfg = _make_config()
    cfg["analysis"] = [{"name": "zz_parity_mean"}]
    cfg["reporting"]["formats"] = ["mock_report", "zz_parity_summary"]
    cfg["intermediates"] = {"save": True, "compress": "none"}
    cfg["qa"] = {"enabled": True, "stages": ["model"], "model": {"plugins": ["zz_parity_qa"]}}
    ctx, err, out = _check("full_run", cfg, tmp_path, monkeypatch,
                           extra=lambda out: {"summary_json": json.loads((out / "summary.json").read_text())})
    assert err is None
    assert "intermediates/model.joblib" in _files(out)
    assert "qa/model/zz_parity_qa/qa.txt" in _files(out)


def test_pipeline_preparer_with_steps(tmp_path, monkeypatch):
    # the pipeline preparer and its steps are built-ins; register them even
    # when this file runs on its own
    ModuleRegistry().discover()
    cfg = _make_config()
    cfg["preparation"] = {"type": "pipeline", "steps": [
        {"name": "split"}, {"name": "concatenate"}, {"name": "delay", "params": {"delays": [1, 2]}}]}
    ctx, err, _ = _check("pipeline_preparer", cfg, tmp_path, monkeypatch)
    assert err is None
    prepare = next(s for s in ctx.run_summary.stages if s.name == "prepare")
    assert [n.id for n in prepare.nodes] == ["prepare:pipeline", "prepare:split", "prepare:concatenate", "prepare:delay"]


def test_failing_analyzer_is_isolated(tmp_path, monkeypatch):
    cfg = _make_config()
    cfg["analysis"] = [{"name": "zz_parity_boom"}, {"name": "zz_parity_mean"}]
    ctx, err, _ = _check("failing_analyzer", cfg, tmp_path, monkeypatch)
    assert err is None
    analyze = next(s for s in ctx.run_summary.stages if s.name == "analyze")
    assert analyze.detail == "1/2 analyzer(s) ok, failed: zz_parity_boom"
    assert ctx.has("analysis.mean_score")


def test_all_reporters_failing_fails_the_report_stage(tmp_path, monkeypatch):
    cfg = _make_config()
    cfg["reporting"]["formats"] = ["zz_parity_fail_reporter"]
    _, err, _ = _check("all_reporters_failing", cfg, tmp_path, monkeypatch)
    assert isinstance(err, StageError)


def test_model_failure_stops_the_run(tmp_path, monkeypatch):
    cfg = _make_config()
    cfg["model"] = {"type": "zz_parity_fail_model", "params": {}}
    ctx, err, _ = _check("model_failure", cfg, tmp_path, monkeypatch)
    assert isinstance(err, StageError) and "model boom" in str(err)
    assert [s.name for s in ctx.run_summary.stages][-1] == "model"


def test_no_reporters_still_records_the_report_stage(tmp_path, monkeypatch):
    cfg = _make_config()
    cfg["reporting"]["formats"] = []
    ctx, err, _ = _check("no_reporters", cfg, tmp_path, monkeypatch)
    assert err is None and ctx.run_summary.stages[-1].detail == "0 artifact(s) saved"


def test_checkpoints(tmp_path, monkeypatch):
    config = _make_config()
    config["checkpoint"] = True

    def checkpoints(out):
        return {"checkpoints": {p.name: sorted(pickle.loads(p.read_bytes()))
                                for p in sorted((out / ".checkpoints").glob("*.pkl"))}}

    _, err, out = _check("checkpoints", config, tmp_path, monkeypatch, extra=checkpoints)
    assert err is None and len(list((out / ".checkpoints").glob("*.pkl"))) == 7


def test_pipeline_orchestrator_runs_on_the_graph_engine(tmp_path, monkeypatch):
    cfg = _make_config()
    cfg["reporting"]["formats"] = []
    cfg["reporting"]["output_dir"] = str(tmp_path / "run")
    monkeypatch.setenv("FMRIFLOW_EVENTS_FILE", str(tmp_path / "events.jsonl"))
    ctx = PipelineOrchestrator(cfg, _make_registry()).run()
    expected = json.loads((GOLDEN_DIR / "subject_no_reporters.json").read_text())
    assert json.loads(json.dumps(_summary(ctx))) == expected["summary"]
    assert sorted(ctx._store) == sorted(expected["context"])


def test_partial_runs_continue_a_context(tmp_path, monkeypatch):
    cfg = _make_config()
    cfg["analysis"] = [{"name": "zz_parity_mean"}]
    cfg["reporting"]["output_dir"] = str(tmp_path / "run")
    monkeypatch.delenv("FMRIFLOW_EVENTS_FILE", raising=False)
    registry = _make_registry()
    first = ["stimuli", "responses", "features", "prepare", "model"]
    ctx = PipelineOrchestrator(cfg, registry).run(stages=first)
    assert [s.name for s in ctx.run_summary.stages] == first
    assert ctx.has("result") and not ctx.has("analysis.mean_score")

    ctx = PipelineOrchestrator(cfg, registry).run(stages=["analyze", "report"], context=ctx)
    assert [s.name for s in ctx.run_summary.stages] == ["analyze", "report"]
    assert ctx.has("analysis.mean_score") and ctx.artifacts

    with pytest.raises(PipelineError):      # the model needs prepared data a fresh context lacks
        PipelineOrchestrator(cfg, registry).run(stages=["model"])
    with pytest.raises(ConfigError):
        PipelineOrchestrator(cfg, registry).run(stages=["nope"])


def test_pipeline_engine_setting(tmp_path, monkeypatch, caplog):
    cfg = _make_config()
    cfg["reporting"]["output_dir"] = str(tmp_path / "api")
    monkeypatch.delenv("FMRIFLOW_EVENTS_FILE", raising=False)
    monkeypatch.delenv("FMRIFLOW_ENGINE", raising=False)
    pipeline = Pipeline(cfg, registry=_make_registry())
    ctx = pipeline.run()
    assert ctx.has("result") and pipeline.last_context is ctx
    assert json.loads((tmp_path / "api" / "graph.json").read_text())["scope"] == "subject"
    monkeypatch.setenv("FMRIFLOW_ENGINE", "legacy")
    with caplog.at_level("WARNING"):
        assert Pipeline(cfg, registry=_make_registry()).engine == "graph"
    assert "retired" in caplog.text
    monkeypatch.setenv("FMRIFLOW_ENGINE", "bogus")
    with pytest.raises(ConfigError):
        Pipeline(cfg, registry=_make_registry())

