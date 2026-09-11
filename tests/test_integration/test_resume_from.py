"""--resume-from continues after the checkpointed stage instead of re-running everything."""

import pytest

from fmriflow.orchestrator import ConfigError
from fmriflow.pipeline import Pipeline
from tests.test_integration.test_pipeline import _make_config, _make_registry


def _checkpointed_config(tmp_path):
    config = _make_config()
    config["checkpoint"] = True
    config.setdefault("reporting", {})["output_dir"] = str(tmp_path)
    return config


def test_resume_from_runs_only_the_following_stages(tmp_path):
    reg = _make_registry()
    config = _checkpointed_config(tmp_path)
    Pipeline(config, registry=reg).run()

    ctx = Pipeline(config, registry=reg).run(resume_from="features")
    assert [s.name for s in ctx.run_summary.stages] == ["prepare", "model", "analyze", "report"]
    assert ctx.has("stimuli") and ctx.has("features")


def test_resume_from_the_last_stage_runs_nothing(tmp_path):
    reg = _make_registry()
    config = _checkpointed_config(tmp_path)
    Pipeline(config, registry=reg).run()

    ctx = Pipeline(config, registry=reg).run(resume_from="report")
    assert ctx.run_summary.stages == []


def test_resume_from_unknown_stage_is_a_config_error(tmp_path):
    with pytest.raises(ConfigError):
        Pipeline(_checkpointed_config(tmp_path), registry=_make_registry()).run(resume_from="nope")
