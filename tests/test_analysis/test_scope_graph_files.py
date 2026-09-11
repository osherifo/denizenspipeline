"""Group and study graphs as files: subject graph bodies, group graphs inside studies,
the CLI, the run manager and the bundled group and study templates."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from fmriflow import cli
from fmriflow.analysis.catalog import NodeCatalog
from fmriflow.analysis.compile_legacy import compile_group_config, compile_study_config, compile_subject_config
from fmriflow.analysis.control import MapSubjects
from fmriflow.analysis.executor import resolve_graph_inputs
from fmriflow.analysis.templates import load_template
from fmriflow.registry import ModuleRegistry
from tests.test_analysis.test_group_study_runs import (  # noqa: F401  (scope_modules is an autouse fixture)
    _group_cfg, _registry, _run_group, _template, scope_modules,
)


@pytest.fixture
def mock_cli(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "_build_registry", _registry)
    monkeypatch.setenv("FMRIFLOW_EVENTS_FILE", str(tmp_path / "events.jsonl"))


def _body_file(tmp_path: Path) -> Path:
    body = compile_subject_config({**_template(), "subject": "$inputs.subject", "experiment": "$inputs.experiment"})
    body.name = "mock_body"
    body.inputs = {"subject": {"kind": "str"},
                   "experiment": {"kind": "str", "required": False, "default": "integration_test"}}
    path = tmp_path / "body.yaml"
    body.save(path)
    return path


def _group_graph(tmp_path: Path, body: Path, **params):
    graph = compile_group_config(_group_cfg(), registry=_registry())
    graph.globals = {"group": "g", "output_dir": str(tmp_path / "graph_run"), "parallel": {"max_workers": 1}}
    graph.node("subject_fanout:subjects").params = {
        "subjects": ["S1", "S2", "S3"], "body": str(body), "inputs": {"experiment": "exp_{subject}"},
        "max_workers": 1, **params}
    return graph


def _stage_view(summary: dict, key: str):
    return [(s["name"], s["status"], [(n["id"], n["status"], n["detail"]) for n in s.get("nodes", [])])
            for s in summary[key]]


def test_group_graph_file_with_a_subject_graph_body(tmp_path, monkeypatch, mock_cli):
    path = tmp_path / "group_graph.yaml"
    _group_graph(tmp_path, _body_file(tmp_path)).save(path)
    assert cli.main(["run", str(path), "--run-id", "gr1"]) == 0

    run_dir = tmp_path / "graph_run" / "gr1"
    summary = json.loads((run_dir / "group_summary.json").read_text())
    subject_graph = json.loads((run_dir / "subjects" / "S2" / "graph.json").read_text())
    assert subject_graph["globals"]["experiment"] == "exp_S2"
    count = json.loads((run_dir / "subjects" / "S2" / "count.json").read_text())
    assert count["with_offset"] is not None           # the second pass ran on the body graph

    # The same group as a group config (stage template) records the same group stages.
    template_run, _, _ = _run_group("graph", _group_cfg(), tmp_path / "template", monkeypatch)
    expected = [(s.name, s.status, [(n.id, n.status, n.detail) for n in s.nodes])
                for s in template_run.group_summary.group_stages]
    assert _stage_view(summary, "group_stages") == expected

    assert cli.main(["run-group", str(path), "--run-id", "gr2"]) == 0
    assert (tmp_path / "graph_run" / "gr2" / "group_summary.json").is_file()


def test_study_graph_file_with_a_group_graph_and_a_group_config(tmp_path, mock_cli):
    group_graph_path = tmp_path / "reading_graph.yaml"
    _group_graph(tmp_path, _body_file(tmp_path)).save(group_graph_path)
    group_config_path = tmp_path / "listening.yaml"
    group_config_path.write_text(yaml.safe_dump(_group_cfg(
        group="group_listening", subjects=["S1", "S2"], group_report=[], group_analyze=[{"name": "zz_group_mean"}])))
    study = compile_study_config({
        "study": "st",
        "groups": [{"name": "reading", "config": str(group_graph_path)},
                   {"name": "listening", "config": str(group_config_path)}],
        "study_analyze": [{"name": "zz_study_count"}], "study_report": [{"name": "zz_study_report"}],
    })
    study.globals = {"study": "st", "output_dir": str(tmp_path / "study_out")}
    path = tmp_path / "study_graph.yaml"
    study.save(path)

    assert cli.main(["run", str(path), "--run-id", "sg"]) == 0
    run_dir = tmp_path / "study_out" / "sg"
    summary = json.loads((run_dir / "study_summary.json").read_text())
    assert summary["status"] == "ok"
    assert summary["group_labels"] == ["reading", "listening"]
    assert (run_dir / "groups" / "reading" / "sg__reading" / "subjects" / "S3" / "graph.json").is_file()
    assert json.loads((run_dir / "study_report.json").read_text()) == {"n": 5}


def test_graph_file_errors_are_reported(tmp_path, mock_cli):
    graph = _group_graph(tmp_path, _body_file(tmp_path))
    graph.node("subject_fanout:subjects").params["subject_template"] = _template()
    path = tmp_path / "bad.yaml"
    graph.save(path)
    assert cli.main(["run", str(path), "--run-id", "bad"]) == 1
    assert not (tmp_path / "graph_run" / "bad" / "group_summary.json").exists()


def test_map_subjects_needs_subjects_and_exactly_one_body():
    assert MapSubjects.validate_params({"subjects": ["a"], "subject_template": {"x": 1}}) == []
    assert MapSubjects.validate_params({"subjects": ["a"], "body": "analyze"}) == []
    assert len(MapSubjects.validate_params({"subjects": ["a"]})) == 1
    assert len(MapSubjects.validate_params({"subjects": ["a"], "body": "b", "subject_template": {"x": 1}})) == 1
    assert len(MapSubjects.validate_params({"subjects": [], "body": "b"})) == 1


@pytest.mark.parametrize("name, scope", [("group_mean", "group"), ("study_group_delta", "study")])
def test_group_and_study_templates(name, scope):
    registry = ModuleRegistry()
    registry.discover()
    graph = load_template(name)
    assert graph.scope == scope
    assert graph.validate(NodeCatalog(registry).discover()) == []
    values = {k: ["s1", "s2"] if k == "subjects" else {} if k == "body_inputs" else f"value_{k}" for k in graph.inputs}
    bound, _ = resolve_graph_inputs(graph, values)
    assert "$inputs." not in bound.to_yaml()


def test_run_manager_launches_group_graphs(tmp_path, monkeypatch):
    from fmriflow.server.services import run_manager as rm

    monkeypatch.setenv("FMRIFLOW_HOME", str(tmp_path / "home"))
    launched = []
    monkeypatch.setattr(rm.RunManager, "_spawn_and_track", lambda self, handle: launched.append(handle))
    graph = load_template("group_mean")
    try:
        rm.RunManager().start_graph_run(graph.to_dict(), inputs={
            "group": "gm", "subjects": ["s1", "s2"], "output_dir": str(tmp_path / "groups")})
        handle = launched[0]
        assert handle.is_group and not handle.is_study
        assert handle.output_dir == str(tmp_path / "groups")
        bound = yaml.safe_load(Path(handle.config_path).read_text())
        assert bound["scope"] == "group" and bound["globals"]["group"] == "gm"
    finally:
        for handle in launched:
            Path(handle.config_path).unlink(missing_ok=True)
