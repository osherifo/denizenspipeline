"""Group and study runs, checked against golden records, plus graph-only behaviour.

The graph runners replaced the group and study orchestrators after matching them on
the group and study cases below: group and study summaries, subject summaries in
memory and on disk, events, group artifacts, subject contexts after the second pass,
and the files written. Those orchestrator runs are kept as records in ``golden/``
(see ``_golden.py``). Utility nodes exist only in graph runs and are left out.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml

from fmriflow import cli
from fmriflow.analysis.catalog import NodeCatalog
from fmriflow.analysis.compile_legacy import compile_group_config, compile_study_config, compile_subject_config
from fmriflow.analysis.scope_runners import GroupGraphRunner, StudyGraphRunner
from fmriflow.core.run_summary import RunSummary
from fmriflow.group_orchestrator import GroupOrchestrator
from fmriflow.modules import _decorators as deco
from fmriflow.study_orchestrator import StudyOrchestrator
from tests.test_analysis._golden import check_golden
from tests.test_integration.test_pipeline import MockFeatureSource, _make_config, _make_registry

REPORTS: list[str] = []


class _GroupMean:
    name = "zz_group_mean"

    def analyze(self, group, config):
        entry = next(e for e in config["group_analyze"] if e["name"] == self.name)
        scale = (entry.get("params") or {}).get("scale", 1)
        means = [float(sr.context.get("result").scores.mean()) for sr in group.subjects
                 if sr.context is not None and sr.context.has("result")]
        group.put("group.mean", scale * sum(means) / max(len(means), 1))

    def validate_config(self, config):
        return []


class _GroupBind:
    name = "zz_group_bind"
    produces_subject_artifact = True

    def analyze(self, group, config):
        group.put("group.offset", 1.5)

    def subject_bindings(self, group):
        return {"offset": group.get("group.offset")}

    def validate_config(self, config):
        return []


class _UseBinding:
    name = "zz_use_binding"
    binding_consumer = True

    def analyze(self, context, config):
        if context.has("external.offset"):
            context.put("analysis.with_offset",
                        float(context.get("result").scores.mean()) + context.get("external.offset"))

    def validate_config(self, config):
        return []


class _CountingReporter:
    name = "zz_count_reporter"

    def report(self, result, context, config):
        REPORTS.append(config["subject"])
        out = Path(config["reporting"]["output_dir"])
        out.mkdir(parents=True, exist_ok=True)
        path = out / "count.json"
        value = context.get("analysis.with_offset") if context.has("analysis.with_offset") else None
        path.write_text(json.dumps({"with_offset": value}))
        return {"count": str(path)}

    def validate_config(self, config):
        return []


class _GroupReport:
    name = "zz_group_report"

    def report(self, group, config):
        path = Path(config["output_dir"]) / "group_report.json"
        path.write_text(json.dumps({"mean": group.get("group.mean"), "n": len(group.subjects)}))
        return {"report": str(path)}

    def validate_config(self, config):
        return []


class _FailModel:
    name = "zz_group_fail_model"

    def fit(self, data, config):
        raise RuntimeError("model boom")

    def validate_config(self, config):
        return []


class _StudyCount:
    name = "zz_study_count"

    def analyze(self, study, config):
        study.put("study.n_subjects", sum(len(g.subjects) for g in study.groups))

    def validate_config(self, config):
        return []


class _StudyReport:
    name = "zz_study_report"

    def report(self, study, config):
        path = Path(config["output_dir"]) / "study_report.json"
        path.write_text(json.dumps({"n": study.get("study.n_subjects")}))
        return {"report": str(path)}

    def validate_config(self, config):
        return []


_MODULES = [
    (deco._group_analyzers, _GroupMean), (deco._group_analyzers, _GroupBind), (deco._analyzers, _UseBinding),
    (deco._reporters, _CountingReporter), (deco._group_reporters, _GroupReport), (deco._models, _FailModel),
    (deco._study_analyzers, _StudyCount), (deco._study_reporters, _StudyReport),
]


@pytest.fixture(autouse=True)
def scope_modules():
    for registry, cls in _MODULES:
        registry[cls.name] = cls
    REPORTS.clear()
    yield
    for registry, cls in _MODULES:
        registry.pop(cls.name, None)


def _registry():
    reg = _make_registry()
    # Group configs are schema-checked, and the schema only knows built-in feature source
    # names: run the mock source under one of them without touching the shared registry.
    reg._feature_sources = {**reg._feature_sources, "filesystem": MockFeatureSource}
    return reg


def _template():
    cfg = _make_config()
    cfg.pop("subject")
    cfg["features"] = [{"name": "mock_feat", "source": "filesystem", "path": "/data/features"}]
    cfg["analysis"] = [{"name": "zz_use_binding"}]
    cfg["reporting"] = {"formats": ["mock_report", "zz_count_reporter"]}
    return cfg


def _group_cfg(**extra):
    cfg = {
        "group": "g",
        "subjects": ["S1", "S2", "S3"],
        "subject_template": _template(),
        "group_analyze": [{"name": "zz_group_mean", "params": {"scale": 2}}, {"name": "zz_group_bind"}],
        "group_report": [{"name": "zz_group_report"}],
        "parallel": {"max_workers": 1},
    }
    cfg.update(extra)
    return cfg


def _events_file(root: Path, name: str, monkeypatch) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{name}_events.jsonl"
    monkeypatch.setenv("FMRIFLOW_EVENTS_FILE", str(path))
    return path


def _read_events(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def _run_group(engine, cfg, root, monkeypatch, *, resume=False, run_id="r1"):
    cfg = copy.deepcopy(cfg)
    cfg["output_dir"] = str(root / engine)
    events = _events_file(root, engine, monkeypatch)
    cls = GroupOrchestrator if engine == "legacy" else GroupGraphRunner
    result = cls(cfg, _registry(), run_id=run_id).run(resume=resume)
    return result, _read_events(events), root / engine / run_id


def _run_study(engine, cfg, root, monkeypatch, *, run_id="s1"):
    cfg = copy.deepcopy(cfg)
    cfg["output_dir"] = str(root / engine)
    events = _events_file(root, engine, monkeypatch)
    cls = StudyOrchestrator if engine == "legacy" else StudyGraphRunner
    result = cls(cfg, _registry(), run_id=run_id).run()
    return result, _read_events(events), root / engine / run_id


_VOLATILE = {"t", "elapsed", "elapsed_s", "timestamp", "ts", "time", "started_at", "finished_at", "total_elapsed_s"}


def _events(events, run_dir: Path):
    out = []
    for e in events:
        if str(e.get("node_id", "")).startswith("utility:"):
            continue
        clean = {k: v for k, v in e.items() if k not in _VOLATILE}
        out.append(json.loads(json.dumps(clean).replace(str(run_dir.parent), "<root>")))
    return out


def _stages(stages):
    return [(s.name, s.status, s.detail,
             [(n.id, n.kind, n.name, n.status, n.detail, sorted(n.outputs)) for n in s.nodes if n.kind != "utility"])
            for s in stages]


def _files(run_dir: Path):
    return sorted(str(p.relative_to(run_dir)) for p in run_dir.rglob("*")
                  if p.is_file() and p.name != "graph.json" and p.suffix != ".log" and ".values" not in p.parts)


def _on_disk(sr):
    return _stages(RunSummary.from_json(Path(sr.run_dir) / "run_summary.json").stages)


def _engine() -> str:
    return "graph"


def _subject_runs(result):
    return [{
        "subject": sr.subject, "status": sr.status,
        "summary": _stages(sr.run_summary.stages), "on_disk": _on_disk(sr),
        "with_offset": (sr.context.get("analysis.with_offset")
                        if sr.context is not None and sr.context.has("analysis.with_offset") else None),
    } for sr in result.subjects]


def _group_record(result, events, run_dir):
    return {
        "group_stages": _stages(result.group_summary.group_stages),
        "subjects": result.group_summary.subjects,
        "subject_runs": _subject_runs(result),
        "artifacts": sorted(result.artifacts),
        "group_mean": result.artifacts.get("group.mean"),
        "events": _events(events, run_dir),
        "files": _files(run_dir),
    }


# ── group ───────────────────────────────────────────────────────────


def test_group_with_group_modules_and_second_pass(tmp_path, monkeypatch):
    result, events, run_dir = _run_group(_engine(), _group_cfg(), tmp_path, monkeypatch)
    assert events and [s.name for s in result.group_summary.group_stages] == [
        "group_collect", "subject_fanout", "group_analyze", "subject_second_pass", "group_report"]
    for sr in result.subjects:
        assert sr.context.get("analysis.with_offset") is not None
    check_golden("group_second_pass", _group_record(result, events, run_dir))
    if _engine() == "graph":
        assert (run_dir / "subjects" / "S1" / "graph.json").is_file()
    assert sorted(REPORTS) == sorted(["S1", "S2", "S3"] * 2)   # first pass and second pass


def test_group_with_a_failing_subject(tmp_path, monkeypatch):
    cfg = _group_cfg(subject_overrides={"S2": {"model": {"type": "zz_group_fail_model"}}})
    result, events, run_dir = _run_group(_engine(), cfg, tmp_path, monkeypatch)
    assert {sr.subject: sr.status for sr in result.subjects}["S2"] == "failed"
    check_golden("group_failing_subject", _group_record(result, events, run_dir))


def test_minimal_second_pass_reruns_only_binding_consumers(tmp_path, monkeypatch):
    graph, _, _ = _run_group("graph", _group_cfg(second_pass="minimal"), tmp_path, monkeypatch)
    assert sorted(REPORTS) == ["S1", "S2", "S3"]      # reporters ran in the first pass only
    for sr in graph.subjects:
        assert sr.context.get("analysis.with_offset") is not None
        analyze = next(s for s in RunSummary.from_json(Path(sr.run_dir) / "run_summary.json").stages
                       if s.name == "analyze")
        assert analyze.detail.startswith("second pass")

    REPORTS.clear()
    _run_group("graph", _group_cfg(), tmp_path / "full", monkeypatch)
    assert sorted(REPORTS) == ["S1", "S1", "S2", "S2", "S3", "S3"]


def test_resume_brings_back_saved_values(tmp_path, monkeypatch):
    cfg = _group_cfg(resume_values="light", group_report=[], group_analyze=[{"name": "zz_group_mean"}])
    first, _, run_dir = _run_group("graph", cfg, tmp_path, monkeypatch, run_id="rr")
    assert (run_dir / "subjects" / "S1" / ".values" / "context.pkl").is_file()

    second, _, _ = _run_group("graph", cfg, tmp_path, monkeypatch, run_id="rr", resume=True)
    assert all(getattr(sr.context, "restored_values", False) for sr in second.subjects)
    analyze = next(s for s in second.group_summary.group_stages if s.name == "group_analyze")
    assert analyze.status == "ok"
    assert second.get("group.mean") == pytest.approx(first.get("group.mean"))

    plain = _group_cfg(group_report=[], group_analyze=[{"name": "zz_group_mean"}])
    _run_group("graph", plain, tmp_path / "plain", monkeypatch, run_id="rp")
    again, _, _ = _run_group("graph", plain, tmp_path / "plain", monkeypatch, run_id="rp", resume=True)
    assert all(sr.context is None for sr in again.subjects)
    assert next(s for s in again.group_summary.group_stages if s.name == "group_analyze").status == "warning"


# ── study ───────────────────────────────────────────────────────────


def _study_cfg(root: Path) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    groups = []
    for label in ("reading", "listening"):
        g = _group_cfg(group=f"group_{label}", subjects=["S1", "S2"], group_report=[],
                       group_analyze=[{"name": "zz_group_mean"}])
        path = root / f"{label}.yaml"
        path.write_text(yaml.safe_dump(g))
        groups.append({"name": label, "config": str(path)})
    return {"study": "st", "groups": groups,
            "study_analyze": [{"name": "zz_study_count"}], "study_report": [{"name": "zz_study_report"}]}


def test_study(tmp_path, monkeypatch):
    cfg = _study_cfg(tmp_path / "configs")
    result, events, run_dir = _run_study(_engine(), cfg, tmp_path, monkeypatch)
    assert result.study_summary.status == "ok"
    assert result.get("study.n_subjects") == 4
    check_golden("study", {
        "status": result.study_summary.status,
        "labels": result.study_summary.group_labels,
        "study_stages": _stages(result.study_summary.study_stages),
        "groups": [{"group_stages": _stages(g.group_summary.group_stages), "subject_runs": _subject_runs(g)}
                   for g in result.groups],
        "artifacts": sorted(result.artifacts),
        "n_subjects": result.get("study.n_subjects"),
        "events": _events(events, run_dir),
        "files": _files(run_dir),
    })


# ── graphs and the CLI ──────────────────────────────────────────────


def test_group_and_study_configs_compile_to_valid_graphs(tmp_path):
    catalog = NodeCatalog(_registry()).discover()
    group = compile_group_config(_group_cfg(), registry=_registry())
    assert [n.type for n in group.topo_order()] == [
        "control:map_subjects", "group_analyzer:zz_group_mean", "group_analyzer:zz_group_bind",
        "control:subject_pass", "group_reporter:zz_group_report"]
    assert group.stages == ["group_collect", "subject_fanout", "group_analyze", "subject_second_pass", "group_report"]
    assert group.node("group_analyze:zz_group_mean").params == {"scale": 2}
    assert group.validate(catalog) == []
    no_binder = compile_group_config(_group_cfg(group_analyze=[{"name": "zz_group_mean"}]), registry=_registry())
    assert "control:subject_pass" not in {n.type for n in no_binder.nodes}

    study = compile_study_config(_study_cfg(tmp_path))
    assert [n.type for n in study.topo_order()] == [
        "control:group", "control:group", "control:study_groups", "study_analyzer:zz_study_count",
        "study_reporter:zz_study_report"]
    assert study.validate(catalog) == []

    subject = compile_subject_config({**_template(), "subject": "S1"})
    subject.nodes.append(group.node("subject_fanout:subjects"))
    assert any("belongs in a group graph" in e for e in subject.validate(catalog))


def test_run_group_cli_accepts_the_retired_engine_flag(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "_build_registry", _registry)
    monkeypatch.setenv("FMRIFLOW_EVENTS_FILE", str(tmp_path / "events.jsonl"))
    path = tmp_path / "group.yaml"
    path.write_text(yaml.safe_dump(_group_cfg(output_dir=str(tmp_path / "out"))))
    assert cli.main(["run-group", str(path), "--engine", "graph", "--run-id", "cli_graph"]) == 0
    assert (tmp_path / "out" / "cli_graph" / "group_summary.json").is_file()
    assert (tmp_path / "out" / "cli_graph" / "subjects" / "S1" / "graph.json").is_file()
    assert cli.main(["run-group", str(path), "--engine", "legacy", "--run-id", "cli_legacy"]) == 0
    assert (tmp_path / "out" / "cli_legacy" / "group_summary.json").is_file()
    assert (tmp_path / "out" / "cli_legacy" / "subjects" / "S1" / "graph.json").is_file()   # runs on the graph engine
