"""Tests for MetricsReporter."""

import json

import numpy as np
import pytest

from fmriflow.core.types import ModelResult
from fmriflow.modules.reporters.metrics import MetricsReporter


@pytest.fixture
def reporter_result():
    rng = np.random.RandomState(42)
    n_voxels = 20
    return ModelResult(
        weights=rng.randn(20, n_voxels).astype(np.float32),
        scores=rng.rand(n_voxels).astype(np.float32),
        alphas=np.full(n_voxels, 100.0),
        feature_names=["feat1", "feat2"],
        feature_dims=[5, 3],
        delays=[1, 2, 3, 4],
    )


class TestMetricsReporter:
    def test_creates_metrics_json(self, tmp_path, reporter_result):
        reporter = MetricsReporter()
        config = {"reporting": {"output_dir": str(tmp_path)}}
        result = reporter.report(reporter_result, None, config)
        metrics_path = tmp_path / "metrics.json"
        assert metrics_path.exists()

    def test_json_has_expected_keys(self, tmp_path, reporter_result):
        reporter = MetricsReporter()
        config = {"reporting": {"output_dir": str(tmp_path)}}
        reporter.report(reporter_result, None, config)

        with open(tmp_path / "metrics.json") as f:
            metrics = json.load(f)

        expected_keys = {
            "mean_score", "median_score", "max_score",
            "n_voxels", "n_significant",
            "feature_names", "feature_dims", "delays",
        }
        assert expected_keys.issubset(set(metrics.keys()))

    def test_metric_values(self, tmp_path, reporter_result):
        reporter = MetricsReporter()
        config = {"reporting": {"output_dir": str(tmp_path)}}
        reporter.report(reporter_result, None, config)

        with open(tmp_path / "metrics.json") as f:
            metrics = json.load(f)

        assert metrics["n_voxels"] == 20
        assert isinstance(metrics["mean_score"], float)
        assert isinstance(metrics["n_significant"], int)
        assert metrics["feature_names"] == ["feat1", "feat2"]

    def test_returns_path_dict(self, tmp_path, reporter_result):
        reporter = MetricsReporter()
        config = {"reporting": {"output_dir": str(tmp_path)}}
        result = reporter.report(reporter_result, None, config)
        assert "metrics" in result
        assert "metrics.json" in result["metrics"]

    def test_validate_config(self):
        reporter = MetricsReporter()
        assert reporter.validate_config({}) == []
