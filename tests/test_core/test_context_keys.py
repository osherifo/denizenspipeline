"""Shared dotted-key resolution for contexts and group results."""

from types import SimpleNamespace

import numpy as np

from fmriflow.context import PipelineContext
from fmriflow.core import context_keys
from fmriflow.core.group_types import GroupResult


def _ctx():
    ctx = PipelineContext({})
    ctx.put("result", SimpleNamespace(scores=np.arange(3), meta={"band": "a"}))
    ctx.put("analysis.fsaverage_scores", np.ones(2))
    return ctx


def test_literal_key_wins_over_walk():
    ctx = _ctx()
    np.testing.assert_array_equal(
        context_keys.resolve_context_key(ctx, "analysis.fsaverage_scores"), np.ones(2))


def test_attribute_and_dict_walk():
    ctx = _ctx()
    np.testing.assert_array_equal(context_keys.resolve_context_key(ctx, "result.scores"), np.arange(3))
    assert context_keys.resolve_context_key(ctx, "result.meta.band") == "a"


def test_missing_keys_and_missing_context_return_none():
    ctx = _ctx()
    assert context_keys.resolve_context_key(ctx, "nope") is None
    assert context_keys.resolve_context_key(ctx, "result.nope") is None
    assert context_keys.resolve_context_key(None, "result.scores") is None


def test_group_key_artifacts_then_attributes():
    g = GroupResult(group_name="demo")
    g.put("group.mean", np.zeros(4))
    g.put("stats", {"n": 3})
    np.testing.assert_array_equal(context_keys.resolve_group_key(g, "group.mean"), np.zeros(4))
    assert context_keys.resolve_group_key(g, "stats.n") == 3
    assert context_keys.resolve_group_key(g, "group_name") == "demo"
    assert context_keys.resolve_group_key(g, "absent") is None
    assert context_keys.resolve_group_key(None, "group.mean") is None


def test_module_helpers_delegate_to_the_shared_resolver():
    from fmriflow.modules.analyzers import algonauts_to_fsaverage, project_to_fsaverage
    from fmriflow.modules.group_analyzers import _helpers as group_helpers
    from fmriflow.modules.reporters import fsaverage_flatmap, semantic_rgb_flatmap
    from fmriflow.modules.study_analyzers import _helpers as study_helpers

    assert study_helpers.resolve_group_key is context_keys.resolve_group_key
    for alias in (project_to_fsaverage._resolve_subject_key,
                  algonauts_to_fsaverage._resolve_subject_key,
                  fsaverage_flatmap._resolve_key,
                  semantic_rgb_flatmap._resolve_key):
        assert alias is context_keys.resolve_context_key
    ctx = _ctx()
    np.testing.assert_array_equal(group_helpers.resolve_subject_key(ctx, "result.scores"), np.arange(3))
