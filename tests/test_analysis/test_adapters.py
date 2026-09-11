"""Adapters run fixed-stage modules as nodes, each node with its own params."""

from __future__ import annotations

import numpy as np
import pytest

from fmriflow.analysis.adapters import NodeEnv, NotRunnableYet
from fmriflow.analysis.catalog import NodeCatalog
from fmriflow.analysis.values import ContextValue
from fmriflow.core.types import FeatureData, FeatureSet, ModelResult, PreparedData, StimulusData
from fmriflow.modules import _decorators as deco
from fmriflow.modules.preparers.pipeline import PipelinePreparer
from tests.conftest import N_TRS, RUN_NAMES
from tests.test_integration.test_pipeline import _make_config, _make_registry


@pytest.fixture
def cat():
    return NodeCatalog(_make_registry()).discover()


def _env(cat, tmp_path, **globals_update):
    g = _make_config()
    g.update(globals_update)
    return NodeEnv(node_id="n", globals=g, registry=cat.registry, output_dir=str(tmp_path))


def test_config_synthesis_replaces_only_the_owned_section(cat, tmp_path):
    env = _env(cat, tmp_path)
    cfg = cat.adapter("model:mock_model").config_for("mock_model", {"alpha": 3, "_section": {"delays": [1]}}, env)
    assert cfg["model"] == {"delays": [1], "type": "mock_model", "params": {"alpha": 3}}
    assert cfg["stimulus"] == _make_config()["stimulus"]
    assert env.globals["model"] == _make_config()["model"]   # globals untouched


def test_subject_chain_through_adapters(cat, tmp_path):
    env = _env(cat, tmp_path)
    stim = cat.invoke("stimulus_loader:mock_stim", {}, {}, env)["stimuli"]
    resp = cat.invoke("response_loader:mock_resp", {}, {}, env)["responses"]
    f1 = cat.invoke("feature_source:mock_source", {"stimuli": stim, "responses": resp},
                    {"feature_name": "f1"}, env)["feature"]
    features = cat.invoke("utility:bundle_features", {"features": [f1]}, {}, env)["features"]
    prepared = cat.invoke("preparer:mock_prep", {"responses": resp, "features": features}, {}, env)["prepared"]
    result = cat.invoke("model:mock_model", {"prepared": prepared}, {}, env)["result"]
    ctx = cat.invoke("utility:collect_context", {"result": result, "prepared": prepared}, {}, env)["context"]
    artifacts = cat.invoke("reporter:mock_report", {"context": [ctx]}, {}, env)["artifacts"]

    assert isinstance(stim, StimulusData) and f1.name == "f1"
    assert isinstance(features, FeatureData) and features.feature_names == ["f1"]
    assert isinstance(prepared, PreparedData) and isinstance(result, ModelResult)
    assert set(ctx) == {"prepared", "result"}
    assert artifacts == {"mock_artifact": "/tmp/mock.json"}


class _KeyWriter:
    """Writes params['value'] under params['output_key'] (first analysis entry with its name)."""
    name = "zz_key_writer"

    def analyze(self, context, config):
        params = next(e for e in config["analysis"] if e["name"] == self.name)["params"]
        context.put(params["output_key"], params["value"])

    def validate_config(self, config):
        return []


def test_repeated_analyzer_nodes_get_their_own_params(cat, tmp_path):
    deco._analyzers["zz_key_writer"] = _KeyWriter
    try:
        cat.discover()
        env = _env(cat, tmp_path)
        seed = ContextValue({"result": "r"})
        a = cat.invoke("analyzer:zz_key_writer", {"context": [seed]}, {"output_key": "analysis.a", "value": 1}, env)
        b = cat.invoke("analyzer:zz_key_writer", {"context": [a["context"]]},
                       {"output_key": "analysis.b", "value": 2}, env)
    finally:
        deco._analyzers.pop("zz_key_writer", None)
    assert dict(b["context"]) == {"result": "r", "analysis.a": 1, "analysis.b": 2}


class _FileReporter:
    name = "zz_file_reporter"

    def report(self, result, context, config):
        opts = config["reporting"][self.name]
        path = f"{config['reporting']['output_dir']}/{opts['filename']}"
        open(path, "w").write(str(result))
        return {"file": path}

    def validate_config(self, config):
        return []


def test_repeated_reporter_nodes_write_their_own_files(cat, tmp_path, mock_model_result):
    deco._reporters["zz_file_reporter"] = _FileReporter
    try:
        cat.discover()
        env = _env(cat, tmp_path)
        ctx = [ContextValue({"result": mock_model_result})]
        first = cat.invoke("reporter:zz_file_reporter", {"context": ctx}, {"filename": "fig_a.txt"}, env)
        second = cat.invoke("reporter:zz_file_reporter", {"context": ctx}, {"filename": "fig_b.txt"}, env)
    finally:
        deco._reporters.pop("zz_file_reporter", None)
    assert first["artifacts"]["file"].endswith("fig_a.txt")
    assert second["artifacts"]["file"].endswith("fig_b.txt")
    assert (tmp_path / "fig_a.txt").is_file() and (tmp_path / "fig_b.txt").is_file()


class _ZzExtractor:
    name = "zz_extractor"
    n_dims = 2

    def extract(self, stimuli, run_names, config):
        dims = int(config.get("dims", 2))
        return FeatureSet(name=self.name, data={rn: np.ones((N_TRS, dims)) for rn in run_names}, n_dims=dims)

    def validate_config(self, config):
        return []


def test_feature_extractor_runs_through_the_compute_source(cat, tmp_path, mock_stimuli):
    deco._feature_extractors["zz_extractor"] = _ZzExtractor
    try:
        cat.discover()
        out = cat.invoke("feature_extractor:zz_extractor", {"stimuli": mock_stimuli},
                         {"feature_name": "renamed", "dims": 3}, _env(cat, tmp_path))
    finally:
        deco._feature_extractors.pop("zz_extractor", None)
    fs = out["feature"]
    assert fs.name == "renamed" and fs.n_dims == 3 and sorted(fs.data) == sorted(RUN_NAMES)


def test_feature_source_takes_run_names_from_responses_when_stimuli_are_empty(cat, tmp_path, mock_responses):
    out = cat.invoke("feature_source:mock_source",
                     {"stimuli": StimulusData(runs={}), "responses": mock_responses}, {}, _env(cat, tmp_path))
    assert sorted(out["feature"].data) == sorted(mock_responses.responses)
    with pytest.raises(ValueError):
        cat.invoke("feature_source:mock_source", {}, {}, _env(cat, tmp_path))


def test_bundle_rejects_duplicate_feature_names(cat, tmp_path):
    fs = FeatureSet(name="same", data={}, n_dims=1)
    with pytest.raises(ValueError):
        cat.invoke("utility:bundle_features", {"features": [fs, fs]}, {}, _env(cat, tmp_path))


class _OkStep:
    def apply(self, state, params):
        pass

    def validate_params(self, params):
        return []


class _BadStep(_OkStep):
    def apply(self, state, params):
        raise RuntimeError("boom")


def test_pipeline_preparer_reports_each_step(mock_responses, mock_feature_data):
    deco._preparation_steps["zz_ok"] = _OkStep
    deco._preparation_steps["zz_bad"] = _BadStep
    calls = []
    try:
        prep = PipelinePreparer()
        prep.on_step = lambda name, elapsed, err: calls.append((name, type(err).__name__ if err else None))
        with pytest.raises(RuntimeError):
            prep.prepare(mock_responses, mock_feature_data,
                         {"preparation": {"steps": [{"name": "zz_ok"}, {"name": "zz_bad"}]}})
    finally:
        deco._preparation_steps.pop("zz_ok", None)
        deco._preparation_steps.pop("zz_bad", None)
    assert calls == [("zz_ok", None), ("zz_bad", "RuntimeError")]


class _ZzQa:
    def report(self, value, config, out_dir):
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "plot.txt"
        path.write_text("qa")
        return {"plot": str(path)}


def test_qa_reporter_writes_under_the_qa_directory(cat, tmp_path, mock_model_result):
    deco._qa_reporters.setdefault("model", {})["zz_qa"] = _ZzQa
    try:
        cat.discover()
        out = cat.invoke("qa_reporter:model.zz_qa", {"value": mock_model_result}, {}, _env(cat, tmp_path))
    finally:
        deco._qa_reporters["model"].pop("zz_qa", None)
    assert out["artifacts"]["plot"] == str(tmp_path / "qa" / "model" / "zz_qa" / "plot.txt")


def test_group_nodes_are_not_runnable_yet(tmp_path):
    cat = NodeCatalog().discover()
    env = NodeEnv(node_id="g", globals={}, registry=cat.registry, output_dir=str(tmp_path))
    with pytest.raises(NotRunnableYet):
        cat.invoke("group_analyzer:voxelwise_mean", {"group": None}, {}, env)


class _NativeScale:
    """Multiply the model scores."""
    name = "zz_native_scale"
    INPUTS = {"result": {"type": "ModelResult", "required": True}}
    OUTPUTS = {"scores": {"type": "Array"}}
    PARAM_SCHEMA = {"factor": {"type": "float", "default": 1.0}}

    def run(self, inputs, params, env):
        return {"scores": inputs["result"].scores * params.get("factor", 1.0)}


def test_native_modules_use_their_declared_ports(cat, tmp_path, mock_model_result):
    deco._analyzers["zz_native_scale"] = _NativeScale
    try:
        cat.discover()
        info = cat.info("analyzer:zz_native_scale")
        out = cat.invoke("analyzer:zz_native_scale", {"result": mock_model_result}, {"factor": 2.0},
                         _env(cat, tmp_path))
    finally:
        deco._analyzers.pop("zz_native_scale", None)
    assert info.native and set(info.inputs) == {"result"} and info.outputs["scores"]["type"] == "Array"
    np.testing.assert_allclose(out["scores"], mock_model_result.scores * 2.0)
