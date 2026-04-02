"""Tests for core data containers and plugin protocols."""

import numpy as np
import pytest

from fmriflow.core.types import (
    FeatureData,
    FeatureExtractor,
    FeatureSet,
    FeatureSource,
    Model,
    ModelResult,
    Preprocessor,
    PreparedData,
    Reporter,
    ResponseData,
    ResponseLoader,
    StimRun,
    StimulusData,
    StimulusLoader,
)


# ── Frozen dataclass construction ────────────────────────────────

class TestStimRun:
    def test_construction(self):
        run = StimRun(name="story1", textgrid="tg", trfile="tr")
        assert run.name == "story1"
        assert run.textgrid == "tg"
        assert run.trfile == "tr"

    def test_defaults(self):
        run = StimRun(name="s", textgrid=None, trfile=None)
        assert run.language == "en"
        assert run.modality == "reading"

    def test_frozen(self):
        run = StimRun(name="s", textgrid=None, trfile=None)
        with pytest.raises(AttributeError):
            run.name = "other"


class TestStimulusData:
    def test_construction(self):
        sd = StimulusData(runs={"a": "run_a"})
        assert "a" in sd.runs
        assert sd.metadata == {}


class TestResponseData:
    def test_construction(self):
        resp = ResponseData(
            responses={"r1": np.zeros((10, 5))},
            mask=np.ones(5, dtype=bool),
            surface="surf",
            transform="xfm",
        )
        assert resp.surface == "surf"
        assert resp.transform == "xfm"
        assert resp.responses["r1"].shape == (10, 5)


class TestFeatureSet:
    def test_construction(self):
        fs = FeatureSet(
            name="feat",
            data={"r1": np.zeros((10, 3))},
            n_dims=3,
        )
        assert fs.name == "feat"
        assert fs.n_dims == 3


class TestFeatureData:
    def test_feature_names(self):
        fs1 = FeatureSet(name="a", data={}, n_dims=3)
        fs2 = FeatureSet(name="b", data={}, n_dims=5)
        fd = FeatureData(features={"a": fs1, "b": fs2})
        assert fd.feature_names == ["a", "b"]

    def test_total_dims(self):
        fs1 = FeatureSet(name="a", data={}, n_dims=3)
        fs2 = FeatureSet(name="b", data={}, n_dims=5)
        fd = FeatureData(features={"a": fs1, "b": fs2})
        assert fd.total_dims == 8


class TestModelResult:
    def test_n_voxels(self):
        mr = ModelResult(
            weights=np.zeros((20, 10)),
            scores=np.zeros(10),
            alphas=np.zeros(10),
            feature_names=["f"],
            feature_dims=[5],
            delays=[1, 2, 3, 4],
        )
        assert mr.n_voxels == 10


# ── Protocol isinstance checks ──────────────────────────────────

class _FakeStimulusLoader:
    name = "fake"
    def load(self, config): ...
    def validate_config(self, config): ...

class _FakeResponseLoader:
    name = "fake"
    def load(self, config): ...
    def validate_config(self, config): ...

class _FakeFeatureSource:
    name = "fake"
    def load(self, run_names, config): ...
    def validate_config(self, config): ...

class _FakeFeatureExtractor:
    name = "fake"
    n_dims = 1
    def extract(self, stimuli, run_names, config): ...
    def validate_config(self, config): ...

class _FakePreprocessor:
    name = "fake"
    def prepare(self, responses, features, config): ...
    def validate_config(self, config): ...

class _FakeModel:
    name = "fake"
    def fit(self, data, config): ...
    def validate_config(self, config): ...

class _FakeReporter:
    name = "fake"
    def report(self, result, context, config): ...
    def validate_config(self, config): ...


class TestProtocols:
    def test_stimulus_loader_protocol(self):
        assert isinstance(_FakeStimulusLoader(), StimulusLoader)

    def test_response_loader_protocol(self):
        assert isinstance(_FakeResponseLoader(), ResponseLoader)

    def test_feature_source_protocol(self):
        assert isinstance(_FakeFeatureSource(), FeatureSource)

    def test_feature_extractor_protocol(self):
        assert isinstance(_FakeFeatureExtractor(), FeatureExtractor)

    def test_preprocessor_protocol(self):
        assert isinstance(_FakePreprocessor(), Preprocessor)

    def test_model_protocol(self):
        assert isinstance(_FakeModel(), Model)

    def test_reporter_protocol(self):
        assert isinstance(_FakeReporter(), Reporter)

    def test_non_compliant_fails(self):
        class NotALoader:
            pass
        assert not isinstance(NotALoader(), StimulusLoader)
