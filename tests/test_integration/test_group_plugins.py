"""Tests for the Phase 2 built-in group analyzers + reporter.

Uses lightweight stub contexts to drive the plugins without spinning up
the real subject pipeline.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from fmriflow.context import PipelineContext
from fmriflow.core.group_types import GroupResult, SubjectResult
from fmriflow.core.run_summary import GroupRunSummary, RunSummary, StageRecord
from fmriflow.modules.group_analyzers.scalar_summary import ScalarSummaryAnalyzer
from fmriflow.modules.group_analyzers.significance_count import (
    SignificanceCountAnalyzer,
)
from fmriflow.modules.group_analyzers.voxelwise_mean import VoxelwiseMeanAnalyzer
from fmriflow.modules.group_reporters.group_summary_html import (
    GroupSummaryHtmlReporter,
)
from fmriflow.registry import ModuleRegistry


# ─── stub helpers ──────────────────────────────────────────────

@dataclass
class _StubResult:
    scores: np.ndarray
    pvals: np.ndarray


def _make_subject(subject: str, scores: np.ndarray,
                  pvals: np.ndarray | None = None,
                  run_dir: Path | None = None) -> SubjectResult:
    if pvals is None:
        pvals = np.full_like(scores, 0.5, dtype=np.float32)
    ctx = PipelineContext({'subject': subject})
    ctx.put('result', _StubResult(scores=scores, pvals=pvals))
    now = datetime.now(timezone.utc).isoformat()
    return SubjectResult(
        subject=subject, experiment='demo',
        run_dir=run_dir or Path('/tmp/stub') / subject,
        run_summary=RunSummary(
            experiment='demo', subject=subject,
            started_at=now, finished_at=now, total_elapsed_s=0.01,
            stages=[StageRecord(name='model', status='ok',
                                elapsed_s=0.01, detail='ok')],
            config_snapshot={},
        ),
        context=ctx,
    )


def _make_group(subjects_data) -> GroupResult:
    """``subjects_data`` is a list of (subject, scores_array, pvals_array_or_none)."""
    g = GroupResult(group_name='demo_group')
    for tup in subjects_data:
        if len(tup) == 2:
            subject, scores = tup
            pvals = None
        else:
            subject, scores, pvals = tup
        g.subjects.append(_make_subject(subject, scores, pvals))
    return g


# ─── registry wiring ───────────────────────────────────────────

def test_builtin_group_plugins_registered():
    reg = ModuleRegistry()
    reg.discover()
    modules = reg.list_modules()
    assert 'voxelwise_mean' in modules['group_analyzers']
    assert 'significance_count' in modules['group_analyzers']
    assert 'scalar_summary' in modules['group_analyzers']
    assert 'group_summary_html' in modules['group_reporters']


# ─── voxelwise_mean ───────────────────────────────────────────

def test_voxelwise_mean_averages_across_subjects():
    g = _make_group([
        ('S1', np.array([1.0, 2.0, 3.0])),
        ('S2', np.array([3.0, 4.0, 5.0])),
        ('S3', np.array([5.0, 6.0, 7.0])),
    ])
    analyzer = VoxelwiseMeanAnalyzer()
    analyzer.analyze(g, {'group_analyze': [{
        'name': 'voxelwise_mean',
        'params': {'input_key': 'result.scores',
                   'output_key': 'group.scores_mean'},
    }]})
    np.testing.assert_allclose(g.get('group.scores_mean'), [3.0, 4.0, 5.0])
    assert g.get('group.scores_mean.n_subjects') == 3
    sem = g.get('group.scores_mean.sem')
    # std with ddof=1 is 2.0 across (1,3,5), SEM = 2/sqrt(3)
    np.testing.assert_allclose(sem, [2.0 / np.sqrt(3)] * 3)


def test_voxelwise_mean_rejects_shape_mismatch():
    g = _make_group([
        ('S1', np.array([1.0, 2.0])),
        ('S2', np.array([3.0, 4.0, 5.0])),
    ])
    with pytest.raises(ValueError, match='inconsistent shapes'):
        VoxelwiseMeanAnalyzer().analyze(g, {})


def test_voxelwise_mean_errors_when_no_subjects_have_key():
    g = GroupResult(group_name='demo')   # zero subjects
    with pytest.raises(ValueError, match='no subjects'):
        VoxelwiseMeanAnalyzer().analyze(g, {})


def test_voxelwise_mean_skips_subjects_missing_key():
    g = _make_group([
        ('S1', np.array([1.0, 2.0])),
        ('S2', np.array([3.0, 4.0])),
    ])
    # Force S2 to have no result in its context.
    g.subjects[1].context._store.pop('result')
    analyzer = VoxelwiseMeanAnalyzer()
    analyzer.analyze(g, {})
    # Only S1 contributed: mean equals S1's array.
    np.testing.assert_allclose(g.get('group.result.scores.mean'),
                               [1.0, 2.0])
    assert g.get('group.result.scores.mean.n_subjects') == 1


# ─── significance_count ───────────────────────────────────────

def test_significance_count_below_threshold():
    g = _make_group([
        ('S1', np.array([0.0, 0.0]), np.array([0.01, 0.40])),
        ('S2', np.array([0.0, 0.0]), np.array([0.03, 0.20])),
        ('S3', np.array([0.0, 0.0]), np.array([0.10, 0.04])),
    ])
    SignificanceCountAnalyzer().analyze(g, {'group_analyze': [{
        'name': 'significance_count',
        'params': {'input_key': 'result.pvals', 'threshold': 0.05,
                   'mode': 'below', 'output_key': 'group.n_sig'},
    }]})
    # Voxel 0: S1 (0.01) and S2 (0.03) pass → 2.  S3 (0.10) fails.
    # Voxel 1: only S3 (0.04) passes → 1.
    np.testing.assert_array_equal(g.get('group.n_sig'), [2, 1])
    assert g.get('group.n_sig.threshold') == 0.05
    assert g.get('group.n_sig.mode') == 'below'


def test_significance_count_above_threshold():
    g = _make_group([
        ('S1', np.array([0.20, 0.05])),
        ('S2', np.array([0.30, 0.15])),
    ])
    SignificanceCountAnalyzer().analyze(g, {'group_analyze': [{
        'name': 'significance_count',
        'params': {'input_key': 'result.scores', 'threshold': 0.10,
                   'mode': 'above'},
    }]})
    # Voxel 0: both pass → 2. Voxel 1: only S2 (0.15) passes → 1.
    np.testing.assert_array_equal(
        g.get('group.result.scores.n_significant'), [2, 1])


def test_significance_count_rejects_bad_mode():
    analyzer = SignificanceCountAnalyzer()
    errors = analyzer.validate_config({'group_analyze': [{
        'name': 'significance_count',
        'params': {'mode': 'sideways'},
    }]})
    assert errors and 'mode' in errors[0]


# ─── scalar_summary ───────────────────────────────────────────

def test_scalar_summary_reduces_with_mean():
    g = _make_group([
        ('S1', np.array([1.0, 3.0])),    # mean = 2
        ('S2', np.array([3.0, 5.0])),    # mean = 4
        ('S3', np.array([5.0, 7.0])),    # mean = 6
    ])
    ScalarSummaryAnalyzer().analyze(g, {'group_analyze': [{
        'name': 'scalar_summary',
        'params': {'input_key': 'result.scores', 'reduce': 'mean',
                   'output_key': 'group.acc'},
    }]})
    summary = g.get('group.acc')
    assert summary['mean'] == pytest.approx(4.0)
    assert summary['n_subjects'] == 3
    # std of [2,4,6] with ddof=1 is 2.0; SEM = 2/sqrt(3)
    assert summary['sem'] == pytest.approx(2.0 / np.sqrt(3))
    assert summary['per_subject'] == {'S1': 2.0, 'S2': 4.0, 'S3': 6.0}


def test_scalar_summary_with_max_reduce():
    g = _make_group([
        ('S1', np.array([1.0, 3.0])),
        ('S2', np.array([10.0, 2.0])),
    ])
    ScalarSummaryAnalyzer().analyze(g, {'group_analyze': [{
        'name': 'scalar_summary',
        'params': {'reduce': 'max', 'output_key': 'g.max'},
    }]})
    summary = g.get('g.max')
    assert summary['per_subject'] == {'S1': 3.0, 'S2': 10.0}
    assert summary['mean'] == pytest.approx(6.5)


def test_scalar_summary_rejects_bad_reduce():
    errors = ScalarSummaryAnalyzer().validate_config({'group_analyze': [{
        'name': 'scalar_summary',
        'params': {'reduce': 'gaussian'},
    }]})
    assert errors and 'reduce' in errors[0]


# ─── group_summary_html ───────────────────────────────────────

def test_group_summary_html_renders(tmp_path):
    g = _make_group([
        ('S1', np.array([1.0, 2.0])),
        ('S2', np.array([3.0, 4.0])),
    ])
    g.put('group.scores_mean', np.array([2.0, 3.0]))
    g.put('group.acc', {'mean': 0.42, 'sem': 0.05, 'n_subjects': 2,
                        'per_subject': {'S1': 0.4, 'S2': 0.44}})
    now = datetime.now(timezone.utc).isoformat()
    g.group_summary = GroupRunSummary(
        group_name=g.group_name, subjects=['S1', 'S2'],
        started_at=now, finished_at=now, total_elapsed_s=1.23,
        subject_summaries=[sr.run_summary for sr in g.subjects],
        group_stages=[StageRecord(name='group_collect', status='ok',
                                  elapsed_s=0.1, detail='')],
        config_snapshot={},
    )
    reporter = GroupSummaryHtmlReporter()
    result = reporter.report(g, {
        'output_dir': str(tmp_path),
        'group_report': [{'name': 'group_summary_html'}],
    })
    out = Path(result['summary'])
    assert out.is_file()
    text = out.read_text()
    assert 'demo_group' in text
    assert 'S1' in text and 'S2' in text
    assert 'group.scores_mean' in text
    assert 'group.acc' in text
    assert 'ndarray' in text
