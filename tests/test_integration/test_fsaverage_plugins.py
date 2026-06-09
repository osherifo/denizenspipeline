"""Registration + graceful-skip tests for the fsaverage / semantic-RGB plugins.

These plugins all reach into pycortex + FreeSurfer at runtime. The tests here
don't try to render anything real — they just verify that:
- every plugin is registered under its expected name
- when the required context keys / pycortex state aren't present, each plugin
  no-ops with a warning instead of raising
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from fmriflow.context import PipelineContext
from fmriflow.core.group_types import GroupResult
from fmriflow.core.run_summary import RunSummary, StageRecord
from fmriflow.core.types import (
    LanguageStim, ModelResult, ResponseData, StimRun, StimulusData,
)
from fmriflow.modules.analyzers.project_to_fsaverage import (
    ProjectToFsaverageAnalyzer,
)
from fmriflow.modules.group_reporters.group_fsaverage_flatmap import (
    GroupFsaverageFlatmapReporter,
)
from fmriflow.modules.reporters.fsaverage_flatmap import FsaverageFlatmapReporter
from fmriflow.modules.reporters.semantic_rgb_flatmap import (
    SemanticRgbFlatmapReporter,
)
from fmriflow.registry import ModuleRegistry


# ─── registration ──────────────────────────────────────────────


def test_all_four_registered():
    reg = ModuleRegistry()
    reg.discover()
    mods = reg.list_modules()
    assert "project_to_fsaverage" in mods["analyzers"]
    assert "fsaverage_flatmap" in mods["reporters"]
    assert "semantic_rgb_flatmap" in mods["reporters"]
    assert "group_fsaverage_flatmap" in mods["group_reporters"]


# ─── project_to_fsaverage analyzer ─────────────────────────────


def _stub_ctx(scores: np.ndarray | None,
              with_responses: bool = True) -> PipelineContext:
    ctx = PipelineContext({"subject": "S1"})
    if scores is not None:
        ctx.put("result", ModelResult(
            weights=np.zeros((5, scores.size)),
            scores=scores, alphas=np.ones(scores.size),
            feature_names=["english1000"],
            feature_dims=[5], delays=[1],
        ))
    if with_responses:
        ctx.put("responses", ResponseData(
            responses={},
            mask=np.array([True]),       # placeholder mask (pre-masked)
            surface="DOES_NOT_EXIST",
            transform="DOES_NOT_EXIST",
        ))
    return ctx


def test_project_to_fsaverage_skips_when_input_key_missing(caplog):
    ctx = _stub_ctx(scores=None, with_responses=True)
    ProjectToFsaverageAnalyzer().analyze(ctx, {"analysis": [{
        "name": "project_to_fsaverage",
        "params": {"input_key": "nope.absent"},
    }]})
    assert not ctx.has("analysis.fsaverage_scores")


def test_project_to_fsaverage_skips_when_responses_missing():
    ctx = _stub_ctx(scores=np.zeros(100), with_responses=False)
    ProjectToFsaverageAnalyzer().analyze(ctx, {"analysis": [{
        "name": "project_to_fsaverage",
    }]})
    assert not ctx.has("analysis.fsaverage_scores")


def test_project_to_fsaverage_skips_on_unknown_surface():
    # pycortex won't find this surface — should skip, not raise.
    ctx = _stub_ctx(scores=np.zeros(100), with_responses=True)
    ProjectToFsaverageAnalyzer().analyze(ctx, {"analysis": [{
        "name": "project_to_fsaverage",
    }]})
    assert not ctx.has("analysis.fsaverage_scores")


# ─── fsaverage_flatmap reporter ────────────────────────────────


def test_fsaverage_flatmap_skips_when_data_missing(tmp_path):
    ctx = _stub_ctx(scores=np.zeros(100), with_responses=True)
    out = FsaverageFlatmapReporter().report(
        ctx.get("result"), ctx,
        {"reporting": {"output_dir": str(tmp_path)}},
    )
    assert out == {}


# ─── semantic_rgb_flatmap reporter ─────────────────────────────


def test_semantic_rgb_flatmap_skips_when_projection_missing(tmp_path):
    ctx = _stub_ctx(scores=np.zeros(100), with_responses=True)
    out = SemanticRgbFlatmapReporter().report(
        ctx.get("result"), ctx,
        {"reporting": {"output_dir": str(tmp_path)}},
    )
    assert out == {}


def test_semantic_rgb_flatmap_skips_when_projection_too_few_components(tmp_path):
    ctx = _stub_ctx(scores=np.zeros(100), with_responses=True)
    # 2-component projection -> can't render RGB (need 3).
    ctx.put("analysis.semantic_pc_projection",
            np.random.default_rng(0).standard_normal((2, 100)))
    out = SemanticRgbFlatmapReporter().report(
        ctx.get("result"), ctx,
        {"reporting": {"output_dir": str(tmp_path)}},
    )
    assert out == {}


# ─── group_fsaverage_flatmap reporter ──────────────────────────


def test_group_fsaverage_flatmap_skips_when_key_missing(tmp_path):
    g = GroupResult(group_name="demo")
    out = GroupFsaverageFlatmapReporter().report(
        g,
        {"output_dir": str(tmp_path),
         "group_report": [{"name": "group_fsaverage_flatmap"}]},
    )
    assert out == {}
