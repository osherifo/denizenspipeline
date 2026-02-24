"""Integration test: full pipeline with synthetic mock plugins."""

import numpy as np
import pytest

from denizenspipeline.context import PipelineContext
from denizenspipeline.core.types import (
    FeatureData,
    FeatureSet,
    ModelResult,
    PreparedData,
    ResponseData,
    StimulusData,
    StimRun,
)
from denizenspipeline.pipeline import Pipeline
from denizenspipeline.registry import PluginRegistry
from denizenspipeline.tests.conftest import (
    MockTextGrid,
    MockTRFile,
    N_FEATURES,
    N_TRS,
    N_VOXELS,
    RUN_NAMES,
)


# ── Lightweight mock plugins ─────────────────────────────────────

class MockStimulusLoader:
    name = "mock_stim"

    def load(self, config):
        runs = {}
        for name in RUN_NAMES:
            runs[name] = StimRun(
                name=name,
                textgrid=MockTextGrid(),
                trfile=MockTRFile(),
            )
        return StimulusData(runs=runs)

    def validate_config(self, config):
        return []


class MockResponseLoader:
    name = "mock_resp"

    def load(self, config):
        rng = np.random.RandomState(0)
        return ResponseData(
            responses={
                name: rng.randn(N_TRS, N_VOXELS).astype(np.float32)
                for name in RUN_NAMES
            },
            mask=np.ones(N_VOXELS, dtype=bool),
            surface="mock_surface",
            transform="mock_transform",
        )

    def validate_config(self, config):
        return []


class MockFeatureSource:
    name = "mock_source"

    def load(self, run_names, config):
        rng = np.random.RandomState(1)
        data = {rn: rng.randn(N_TRS, N_FEATURES).astype(np.float32) for rn in run_names}
        return FeatureSet(name=config.get("name", "mock"), data=data, n_dims=N_FEATURES)

    def validate_config(self, config):
        return []


class MockPreprocessor:
    name = "mock_prep"

    def prepare(self, responses, features, config):
        rng = np.random.RandomState(2)
        n_delayed = N_FEATURES * 4
        n_train = N_TRS * 2
        n_test = N_TRS
        return PreparedData(
            X_train=rng.randn(n_train, n_delayed).astype(np.float32),
            Y_train=rng.randn(n_train, N_VOXELS).astype(np.float32),
            X_test=rng.randn(n_test, n_delayed).astype(np.float32),
            Y_test=rng.randn(n_test, N_VOXELS).astype(np.float32),
            feature_names=["mock_feat"],
            feature_dims=[N_FEATURES],
            delays=[1, 2, 3, 4],
            train_runs=["story1", "story2"],
            test_runs=["story3"],
        )

    def validate_config(self, config):
        return []


class MockModel:
    name = "mock_model"

    def fit(self, data, config):
        rng = np.random.RandomState(3)
        n_delayed = data.X_train.shape[1]
        n_voxels = data.Y_train.shape[1]
        return ModelResult(
            weights=rng.randn(n_delayed, n_voxels).astype(np.float32),
            scores=rng.rand(n_voxels).astype(np.float32),
            alphas=np.full(n_voxels, 100.0),
            feature_names=data.feature_names,
            feature_dims=data.feature_dims,
            delays=data.delays,
        )

    def validate_config(self, config):
        return []


class MockReporter:
    name = "mock_report"

    def report(self, result, context, config):
        return {"mock_artifact": "/tmp/mock.json"}

    def validate_config(self, config):
        return []


# ── Helpers ──────────────────────────────────────────────────────

def _make_registry():
    """Create a registry with only mock plugins."""
    reg = PluginRegistry()
    reg._stimulus_loaders["mock_stim"] = MockStimulusLoader
    reg._response_loaders["mock_resp"] = MockResponseLoader
    reg._feature_sources["mock_source"] = MockFeatureSource
    reg._preprocessors["mock_prep"] = MockPreprocessor
    reg._models["mock_model"] = MockModel
    reg._reporters["mock_report"] = MockReporter
    return reg


def _make_config():
    return {
        "experiment": "integration_test",
        "subject": "mock_subj",
        "stimulus": {"loader": "mock_stim"},
        "response": {"loader": "mock_resp"},
        "features": [
            {"name": "mock_feat", "source": "mock_source"},
        ],
        "preprocessing": {"type": "mock_prep"},
        "model": {"type": "mock_model", "params": {}},
        "split": {"test_runs": ["story3"]},
        "reporting": {"formats": ["mock_report"], "output_dir": "/tmp/test_results"},
    }


# ── Tests ────────────────────────────────────────────────────────

class TestPipelineFullRun:
    def test_pipeline_completes_all_stages(self):
        reg = _make_registry()
        config = _make_config()
        pipeline = Pipeline(config, registry=reg)
        ctx = pipeline.run()

        assert ctx.has("stimuli")
        assert ctx.has("responses")
        assert ctx.has("features")
        assert ctx.has("prepared")
        assert ctx.has("result")

    def test_context_types(self):
        reg = _make_registry()
        config = _make_config()
        pipeline = Pipeline(config, registry=reg)
        ctx = pipeline.run()

        assert isinstance(ctx.get("stimuli"), StimulusData)
        assert isinstance(ctx.get("responses"), ResponseData)
        assert isinstance(ctx.get("features"), FeatureData)
        assert isinstance(ctx.get("prepared"), PreparedData)
        assert isinstance(ctx.get("result"), ModelResult)

    def test_artifacts_stored(self):
        reg = _make_registry()
        config = _make_config()
        pipeline = Pipeline(config, registry=reg)
        ctx = pipeline.run()

        arts = ctx.artifacts
        assert "mock_report" in arts
        assert "mock_artifact" in arts["mock_report"]


class TestPipelinePartialRun:
    def test_run_subset_of_stages(self):
        reg = _make_registry()
        config = _make_config()
        pipeline = Pipeline(config, registry=reg)
        ctx = pipeline.run(stages=["stimuli", "responses"])

        assert ctx.has("stimuli")
        assert ctx.has("responses")
        assert not ctx.has("features")
        assert not ctx.has("prepared")
        assert not ctx.has("result")

    def test_run_single_stage(self):
        reg = _make_registry()
        config = _make_config()
        pipeline = Pipeline(config, registry=reg)
        ctx = pipeline.run(stages=["stimuli"])

        assert ctx.has("stimuli")
        assert not ctx.has("responses")

    def test_resume_with_context(self):
        reg = _make_registry()
        config = _make_config()
        pipeline = Pipeline(config, registry=reg)

        # Run first two stages
        ctx = pipeline.run(stages=["stimuli", "responses"])

        # Continue with features using existing context
        ctx2 = pipeline.run(stages=["features"], context=ctx)
        assert ctx2.has("stimuli")
        assert ctx2.has("responses")
        assert ctx2.has("features")
