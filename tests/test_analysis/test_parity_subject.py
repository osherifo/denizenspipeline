"""The graph engine reproduces the stage orchestrator on the same subject configs.

Each case runs one config through both engines and compares the context
values, artifacts, run summary (stages and per-node records), the event
stream, and the files written (intermediates, QA, reporter outputs).
Utility nodes exist only in the graph and are left out of the comparison;
preparation-step records compare on id, kind, name and status because the
graph engine times each step for real.
"""

from __future__ import annotations

import copy
import dataclasses
import json
from pathlib import Path

import numpy as np
import pytest

from fmriflow.analysis.catalog import NodeCatalog
from fmriflow.analysis.executor import GraphExecutor, run_subject_config
from fmriflow.core.types import StimulusData
from fmriflow.exceptions import ConfigError, StageError
from fmriflow.modules import _decorators as deco
from fmriflow.orchestrator import PipelineOrchestrator
from fmriflow.pipeline import Pipeline
from fmriflow.registry import ModuleRegistry
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


def _run(engine, config, tmp_path, monkeypatch):
    cfg = copy.deepcopy(config)
    out = tmp_path / engine
    cfg["reporting"]["output_dir"] = str(out)
    events = tmp_path / f"{engine}.jsonl"
    monkeypatch.setenv("FMRIFLOW_EVENTS_FILE", str(events))
    registry = _make_registry()
    error = None
    if engine == "legacy":
        orch = PipelineOrchestrator(cfg, registry)
        try:
            orch.run()
        except Exception as exc:
            error = exc
        ctx = orch.ctx
    else:
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


def _assert_same(a, b, path="value"):
    if isinstance(a, StimulusData):
        assert isinstance(b, StimulusData) and list(a.runs) == list(b.runs), path
    elif isinstance(a, np.ndarray):
        np.testing.assert_array_equal(a, b, err_msg=path)
    elif dataclasses.is_dataclass(a):
        assert type(a) is type(b), path
        for f in dataclasses.fields(a):
            _assert_same(getattr(a, f.name), getattr(b, f.name), f"{path}.{f.name}")
    elif isinstance(a, dict):
        assert list(a) == list(b), path
        for k in a:
            _assert_same(a[k], b[k], f"{path}[{k!r}]")
    else:
        assert a == b, path


def _assert_parity(config, tmp_path, monkeypatch):
    legacy_ctx, legacy_err, legacy_events, legacy_out = _run("legacy", config, tmp_path, monkeypatch)
    graph_ctx, graph_err, graph_events, graph_out = _run("graph", config, tmp_path, monkeypatch)

    # guard against vacuous passes: both engines really ran and emitted events
    assert _events(legacy_events) and _summary(legacy_ctx)
    assert any(e.get("kind") == "utility" for e in graph_events)
    assert type(graph_err) is type(legacy_err)
    assert str(graph_err) == str(legacy_err)
    assert _summary(graph_ctx) == _summary(legacy_ctx)
    assert _events(graph_events) == _events(legacy_events)
    assert sorted(graph_ctx._store) == sorted(legacy_ctx._store)
    for key in legacy_ctx._store:
        _assert_same(legacy_ctx._store[key], graph_ctx._store[key], key)
    legacy_artifacts = {k: {n: str(Path(p).relative_to(legacy_out)) if str(p).startswith(str(legacy_out)) else p
                            for n, p in v.items()} for k, v in legacy_ctx.artifacts.items()}
    graph_artifacts = {k: {n: str(Path(p).relative_to(graph_out)) if str(p).startswith(str(graph_out)) else p
                           for n, p in v.items()} for k, v in graph_ctx.artifacts.items()}
    assert graph_artifacts == legacy_artifacts
    assert _files(graph_out) == _files(legacy_out)
    return legacy_ctx, graph_ctx, legacy_err


def test_full_run_with_analyzers_reporters_intermediates_and_qa(tmp_path, monkeypatch):
    cfg = _make_config()
    cfg["analysis"] = [{"name": "zz_parity_mean"}]
    cfg["reporting"]["formats"] = ["mock_report", "zz_parity_summary"]
    cfg["intermediates"] = {"save": True, "compress": "none"}
    cfg["qa"] = {"enabled": True, "stages": ["model"], "model": {"plugins": ["zz_parity_qa"]}}
    legacy_ctx, graph_ctx, err = _assert_parity(cfg, tmp_path, monkeypatch)
    assert err is None
    assert "intermediates/model.joblib" in _files(tmp_path / "graph")
    assert "qa/model/zz_parity_qa/qa.txt" in _files(tmp_path / "graph")
    assert (tmp_path / "graph" / "summary.json").read_text() == (tmp_path / "legacy" / "summary.json").read_text()


def test_pipeline_preparer_with_steps(tmp_path, monkeypatch):
    # the pipeline preparer and its steps are built-ins; register them even
    # when this file runs on its own
    ModuleRegistry().discover()
    cfg = _make_config()
    cfg["preparation"] = {"type": "pipeline", "steps": [
        {"name": "split"}, {"name": "concatenate"}, {"name": "delay", "params": {"delays": [1, 2]}}]}
    legacy_ctx, graph_ctx, err = _assert_parity(cfg, tmp_path, monkeypatch)
    assert err is None
    prepare = next(s for s in graph_ctx.run_summary.stages if s.name == "prepare")
    assert [n.id for n in prepare.nodes] == ["prepare:pipeline", "prepare:split", "prepare:concatenate", "prepare:delay"]


def test_failing_analyzer_is_isolated(tmp_path, monkeypatch):
    cfg = _make_config()
    cfg["analysis"] = [{"name": "zz_parity_boom"}, {"name": "zz_parity_mean"}]
    legacy_ctx, graph_ctx, err = _assert_parity(cfg, tmp_path, monkeypatch)
    assert err is None
    analyze = next(s for s in graph_ctx.run_summary.stages if s.name == "analyze")
    assert analyze.detail == "1/2 analyzer(s) ok, failed: zz_parity_boom"
    assert graph_ctx.has("analysis.mean_score")


def test_all_reporters_failing_fails_the_report_stage(tmp_path, monkeypatch):
    cfg = _make_config()
    cfg["reporting"]["formats"] = ["zz_parity_fail_reporter"]
    _, _, err = _assert_parity(cfg, tmp_path, monkeypatch)
    assert isinstance(err, StageError)


def test_model_failure_stops_the_run(tmp_path, monkeypatch):
    cfg = _make_config()
    cfg["model"] = {"type": "zz_parity_fail_model", "params": {}}
    legacy_ctx, graph_ctx, err = _assert_parity(cfg, tmp_path, monkeypatch)
    assert isinstance(err, StageError) and "model boom" in str(err)
    assert [s.name for s in graph_ctx.run_summary.stages][-1] == "model"


def test_no_reporters_still_records_the_report_stage(tmp_path, monkeypatch):
    cfg = _make_config()
    cfg["reporting"]["formats"] = []
    _, graph_ctx, err = _assert_parity(cfg, tmp_path, monkeypatch)
    assert err is None and graph_ctx.run_summary.stages[-1].detail == "0 artifact(s) saved"


def test_pipeline_api_graph_engine(tmp_path, monkeypatch):
    cfg = _make_config()
    cfg["reporting"]["output_dir"] = str(tmp_path / "api")
    monkeypatch.delenv("FMRIFLOW_EVENTS_FILE", raising=False)
    pipeline = Pipeline(cfg, registry=_make_registry(), engine="graph")
    ctx = pipeline.run()
    assert ctx.has("result") and pipeline.last_context is ctx
    assert json.loads((tmp_path / "api" / "graph.json").read_text())["scope"] == "subject"
    with pytest.raises(ConfigError):
        pipeline.run(stages=["model"])
    monkeypatch.setenv("FMRIFLOW_ENGINE", "graph")
    assert Pipeline(cfg, registry=_make_registry()).engine == "graph"
    monkeypatch.setenv("FMRIFLOW_ENGINE", "bogus")
    with pytest.raises(ConfigError):
        Pipeline(cfg, registry=_make_registry())


def test_checkpoints_match(tmp_path, monkeypatch):
    import pickle

    config = _make_config()
    config["checkpoint"] = True
    legacy_out = _run("legacy", config, tmp_path, monkeypatch)[3]
    graph_out = _run("graph", config, tmp_path, monkeypatch)[3]

    def names(out):
        return sorted(p.name for p in (out / ".checkpoints").glob("*.pkl"))

    assert names(legacy_out) == names(graph_out)
    assert len(names(legacy_out)) == 7
    for name in names(legacy_out):
        a = pickle.loads((legacy_out / ".checkpoints" / name).read_bytes())
        b = pickle.loads((graph_out / ".checkpoints" / name).read_bytes())
        assert sorted(a) == sorted(b), name
