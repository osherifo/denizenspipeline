"""Graph files through the CLI, the run manager, the run views and the HTTP routes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from fmriflow import cli
from fmriflow.analysis.compile_legacy import compile_subject_config
from fmriflow.analysis.graph import AnalysisGraph
from fmriflow.exceptions import ConfigError
from fmriflow.server.services.run_graph import build_graph_run_graph
from tests.test_integration.test_pipeline import _make_config, _make_registry


def _stage_config(tmp_path: Path) -> dict:
    cfg = _make_config()
    cfg["reporting"]["output_dir"] = str(tmp_path / "out")
    return cfg


def _graph_file(tmp_path: Path) -> tuple[Path, AnalysisGraph]:
    graph = compile_subject_config(_stage_config(tmp_path), name="mock")
    path = tmp_path / "graph.yaml"
    graph.save(path)
    return path, graph


@pytest.fixture
def raw_config_loader(monkeypatch):
    """Skip the stage-config schema, which only accepts built-in feature source names."""
    import fmriflow.config.loader as loader
    monkeypatch.setattr(loader, "load_config", lambda path: yaml.safe_load(Path(path).read_text()))


@pytest.fixture
def mock_cli(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "_build_registry", _make_registry)
    monkeypatch.setenv("FMRIFLOW_EVENTS_FILE", str(tmp_path / "events.jsonl"))


# ── CLI ─────────────────────────────────────────────────────────────


def test_cli_runs_a_graph_file(tmp_path, mock_cli):
    path, _ = _graph_file(tmp_path)
    assert cli.main(["run", str(path)]) == 0
    out = tmp_path / "out"
    assert (out / "graph.json").is_file()
    summary = json.loads((out / "run_summary.json").read_text())
    assert [s["name"] for s in summary["stages"]] == [
        "stimuli", "responses", "features", "prepare", "model", "analyze", "report"]
    assert all(s["status"] == "ok" for s in summary["stages"])


def test_cli_graph_inputs_and_refused_flags(tmp_path, mock_cli):
    path, graph = _graph_file(tmp_path)
    graph.inputs = {"out": {"kind": "dir"}}
    graph.globals["reporting"]["output_dir"] = "$inputs.out"
    graph.save(path)
    assert cli.main(["run", str(path)]) == 1
    assert cli.main(["run", str(path), "--engine", "legacy"]) == 1
    assert cli.main(["run", str(path), "--resume-from", "model"]) == 1
    bound = tmp_path / "bound"
    assert cli.main(["run", str(path), "--input", f"out={bound}"]) == 0
    assert (bound / "graph.json").is_file()


def test_cli_graph_compile_and_validate(tmp_path, mock_cli, raw_config_loader):
    cfg_path = tmp_path / "stage.yaml"
    cfg_path.write_text(yaml.safe_dump(_stage_config(tmp_path)))
    out = tmp_path / "compiled.yaml"
    assert cli.main(["graph", "compile", str(cfg_path), "-o", str(out)]) == 0
    graph = AnalysisGraph.load(out)
    assert "model:mock_model" in {n.id for n in graph.nodes}
    assert cli.main(["graph", "validate", str(out)]) == 0
    assert cli.main(["graph", "validate", str(cfg_path)]) == 0
    graph.edges = []
    graph.save(out)
    assert cli.main(["graph", "validate", str(out)]) == 1


# ── run manager ─────────────────────────────────────────────────────


def test_run_manager_launches_graphs(tmp_path, monkeypatch):
    from fmriflow.server.services import run_manager as rm

    monkeypatch.setenv("FMRIFLOW_HOME", str(tmp_path / "home"))
    launched = []
    monkeypatch.setattr(rm.RunManager, "_spawn_and_track", lambda self, handle: launched.append(handle))
    manager = rm.RunManager()
    graph = AnalysisGraph.from_dict({
        "name": "g",
        "inputs": {"subject": {"kind": "str"}},
        "globals": {"subject": "$inputs.subject", "reporting": {"output_dir": str(tmp_path / "results")}},
        "nodes": [{"id": "m", "type": "reporter:metrics"}],
        "edges": [],
    })
    try:
        run_id = manager.start_graph_run(graph.to_dict(), inputs={"subject": "sub01"})
        bound = yaml.safe_load(Path(launched[0].config_path).read_text())
        assert bound["globals"]["subject"] == "sub01"
        assert run_id in bound["globals"]["reporting"]["output_dir"]
        assert "$inputs." not in json.dumps(bound)

        with pytest.raises(ConfigError):
            manager.start_graph_run(graph.to_dict())

        graph.run_defaults = {"inputs": {"subject": "sub02"}}
        saved = tmp_path / "g.yaml"
        graph.save(saved)
        manager.start_run_from_config(str(saved))
        assert yaml.safe_load(Path(launched[1].config_path).read_text())["globals"]["subject"] == "sub02"
    finally:
        for handle in launched:
            Path(handle.config_path).unlink(missing_ok=True)


# ── run views ───────────────────────────────────────────────────────


def test_run_graph_is_built_from_the_executed_graph(tmp_path):
    graph = compile_subject_config(_stage_config(tmp_path))
    records = [{"name": "stimuli", "status": "ok", "elapsed_s": 1.0},
               {"name": "features", "status": "failed", "detail": "boom"}]
    run_graph = build_graph_run_graph(graph.to_dict(), records, _make_registry())
    stages = [n for n in run_graph.nodes if n.kind == "stage"]
    assert [s.stage for s in stages] == graph.stages
    children = {s.stage: s.children for s in stages}
    assert "utility:bundle_features" in children["features"]
    assert "model:mock_model" in children["model"]
    assert len(run_graph.edges) == len(stages) - 1
    status = {s.stage: s.status for s in stages}
    assert (status["stimuli"], status["features"], status["model"]) == ("ok", "failed", "pending")


# ── HTTP routes ─────────────────────────────────────────────────────


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FMRIFLOW_HOME", str(tmp_path / "home"))
    from fmriflow.server.app import create_app
    return TestClient(create_app())


def test_graph_routes(client, tmp_path):
    templates = {t["name"]: t for t in client.get("/api/analysis/graphs/templates").json()["templates"]}
    assert templates["analyze"]["tier"] == "bundled"
    assert templates["analyze"]["scope"] == "subject"
    graph = client.get("/api/analysis/graphs/templates/analyze").json()["graph"]
    assert client.get("/api/analysis/graphs/templates/nope").status_code == 404

    check = client.post("/api/analysis/graphs/validate", json={"graph": graph}).json()
    assert not check["ok"] and any("needs a value" in e for e in check["errors"])

    saved = client.put("/api/analysis/graphs/mine", json={"graph": graph}).json()
    assert saved["saved"] and saved["errors"] == []
    assert [g["name"] for g in client.get("/api/analysis/graphs").json()["graphs"]] == ["mine"]
    assert client.get("/api/analysis/graphs/mine").json()["graph"]["nodes"] == graph["nodes"]
    assert client.get("/api/analysis/graphs/nope").status_code == 404
    body = client.get("/api/configs").json()
    rows = body if isinstance(body, list) else body.get("configs", [])
    assert any(r["filename"] == "mine.yaml" and r["format"] == "graph" for r in rows)

    calls = []
    client.app.state.run_manager.start_graph_run = (
        lambda doc, inputs=None, overrides=None, source="": calls.append((doc, inputs, source)) or "run123")
    started = client.post("/api/analysis/graphs/run", json={"graph_name": "mine", "inputs": {"subject": "sub01"}})
    assert started.json()["run_id"] == "run123"
    assert calls[0][1] == {"subject": "sub01"} and calls[0][2] == "mine"
    assert client.post("/api/analysis/graphs/run", json={}).status_code == 400

    assert client.delete("/api/analysis/graphs/mine").json()["deleted"]
    assert client.delete("/api/analysis/graphs/mine").status_code == 404

    user = client.post("/api/analysis/graphs/templates", json={"name": "t1", "graph": graph}).json()
    assert user["tier"] == "user" and user["warnings"] == []
    assert client.delete("/api/analysis/graphs/templates/analyze").status_code == 403
    assert client.delete("/api/analysis/graphs/templates/t1").json()["deleted"]


def test_compile_route(client, tmp_path, raw_config_loader):
    compiled = client.post("/api/analysis/graphs/compile", json={"config": _stage_config(tmp_path)})
    assert compiled.status_code == 200, compiled.text
    assert "model:mock_model" in {n["id"] for n in compiled.json()["graph"]["nodes"]}
    assert client.post("/api/analysis/graphs/compile", json={}).status_code == 400
    group = client.post("/api/analysis/graphs/compile", json={"config": {"group": "g", "subjects": ["a"]}})
    assert group.status_code == 400
