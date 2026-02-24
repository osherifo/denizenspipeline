"""Tests for default configuration values."""

from denizenspipeline.config.defaults import DEFAULT_CONFIG


class TestDefaultConfig:
    def test_has_expected_top_level_keys(self):
        expected_keys = {"stimulus", "response", "preprocessing", "model", "reporting"}
        assert expected_keys.issubset(set(DEFAULT_CONFIG.keys()))

    def test_stimulus_defaults(self):
        stim = DEFAULT_CONFIG["stimulus"]
        assert isinstance(stim, dict)
        assert stim["loader"] == "textgrid"
        assert stim["language"] == "en"
        assert stim["modality"] == "reading"

    def test_response_defaults(self):
        resp = DEFAULT_CONFIG["response"]
        assert isinstance(resp, dict)
        assert resp["loader"] == "cloud"

    def test_preprocessing_defaults(self):
        prep = DEFAULT_CONFIG["preprocessing"]
        assert isinstance(prep, dict)
        assert isinstance(prep["trim_start"], int)
        assert isinstance(prep["trim_end"], int)
        assert isinstance(prep["delays"], list)
        assert isinstance(prep["zscore"], bool)

    def test_model_defaults(self):
        model = DEFAULT_CONFIG["model"]
        assert isinstance(model, dict)
        assert model["type"] == "bootstrap_ridge"
        assert isinstance(model["params"], dict)

    def test_reporting_defaults(self):
        reporting = DEFAULT_CONFIG["reporting"]
        assert isinstance(reporting, dict)
        assert isinstance(reporting["formats"], list)
        assert isinstance(reporting["output_dir"], str)
