"""Unit tests for the Phase 2 built-in study plugins."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from fmriflow.context import PipelineContext
from fmriflow.core.group_types import GroupResult, SubjectResult
from fmriflow.core.run_summary import RunSummary
from fmriflow.core.study_types import StudyResult
from fmriflow.modules.study_analyzers.cohen_d_across_groups import (
    CohenDAcrossGroupsAnalyzer,
)
from fmriflow.modules.study_analyzers.group_delta import GroupDeltaAnalyzer
from fmriflow.modules.study_reporters.study_summary_html import (
    StudySummaryHtmlReporter,
)


# ─── helpers ───────────────────────────────────────────────────


def _empty_summary(subject: str) -> RunSummary:
    return RunSummary(
        experiment='demo', subject=subject,
        started_at='', finished_at='', total_elapsed_s=0.0,
    )


def _group(label: str, group_name: str,
           artifacts: dict | None = None,
           subject_arrays: dict[str, np.ndarray] | None = None) -> GroupResult:
    """Build a GroupResult with optional artifacts + per-subject context arrays."""
    g = GroupResult(group_name=group_name)
    g.study_label = label
    if artifacts:
        g.artifacts.update(artifacts)
    if subject_arrays:
        for subject, arr in subject_arrays.items():
            ctx = PipelineContext({})
            ctx.put('analysis.fsaverage_scores', arr)
            g.subjects.append(SubjectResult(
                subject=subject, experiment='demo',
                run_dir=Path('/tmp/fake'),
                run_summary=_empty_summary(subject),
                context=ctx,
            ))
    return g


def _study(groups: list[GroupResult]) -> StudyResult:
    return StudyResult(study_name='demo_study', groups=groups)


def _cfg(analyzer_name: str, params: dict) -> dict:
    return {'study_analyze': [{'name': analyzer_name, 'params': params}]}


# ─── group_delta ───────────────────────────────────────────────


def test_group_delta_voxelwise_subtraction():
    a = _group('reading', 'group_a',
               artifacts={'group.scores_mean': np.array([1.0, 2.0, 3.0])})
    b = _group('listening', 'group_b',
               artifacts={'group.scores_mean': np.array([0.5, 1.5, 2.5])})
    study = _study([a, b])
    cfg = _cfg('group_delta', {
        'input_key': 'group.scores_mean',
        'a': 'reading', 'b': 'listening',
        'output_key': 'study.delta',
    })
    GroupDeltaAnalyzer().analyze(study, cfg)
    assert np.allclose(study.get('study.delta'), [0.5, 0.5, 0.5])
    meta = study.get('study.delta.meta')
    assert meta['minuend'] == 'reading'
    assert meta['subtrahend'] == 'listening'


def test_group_delta_shape_mismatch_raises():
    a = _group('a', 'group_a', artifacts={'k': np.zeros(10)})
    b = _group('b', 'group_b', artifacts={'k': np.zeros(20)})
    study = _study([a, b])
    cfg = _cfg('group_delta', {
        'input_key': 'k', 'a': 'a', 'b': 'b', 'output_key': 'study.x',
    })
    with pytest.raises(ValueError) as ei:
        GroupDeltaAnalyzer().analyze(study, cfg)
    assert 'shape mismatch' in str(ei.value)


def test_group_delta_missing_key_raises():
    a = _group('a', 'group_a', artifacts={'k': np.zeros(10)})
    b = _group('b', 'group_b')  # b has nothing under 'k'
    study = _study([a, b])
    cfg = _cfg('group_delta', {
        'input_key': 'k', 'a': 'a', 'b': 'b', 'output_key': 'study.x',
    })
    with pytest.raises(ValueError) as ei:
        GroupDeltaAnalyzer().analyze(study, cfg)
    assert 'missing from group' in str(ei.value)


def test_group_delta_unknown_label_raises():
    a = _group('a', 'group_a', artifacts={'k': np.zeros(3)})
    study = _study([a])
    cfg = _cfg('group_delta', {
        'input_key': 'k', 'a': 'a', 'b': 'NOT_A_REAL_LABEL',
        'output_key': 'study.x',
    })
    with pytest.raises(KeyError):
        GroupDeltaAnalyzer().analyze(study, cfg)


def test_group_delta_validate_config_requires_params():
    cfg = _cfg('group_delta', {'a': 'x'})  # missing input_key + b
    errors = GroupDeltaAnalyzer().validate_config(cfg)
    assert any('input_key' in e for e in errors)
    assert any('.b' in e for e in errors)


# ─── cohen_d_across_groups ─────────────────────────────────────


def test_cohen_d_voxelwise():
    rng = np.random.RandomState(0)
    # Group A: 4 subjects with mean accuracy 0.5 ± 0.1
    a = _group(
        'a', 'group_a',
        subject_arrays={
            f'S{i}': 0.5 + 0.1 * rng.randn(3) for i in range(4)
        },
    )
    # Group B: 4 subjects with mean accuracy 0.3 ± 0.1
    b = _group(
        'b', 'group_b',
        subject_arrays={
            f'S{i}': 0.3 + 0.1 * rng.randn(3) for i in range(4)
        },
    )
    study = _study([a, b])
    cfg = _cfg('cohen_d_across_groups', {
        'input_key': 'analysis.fsaverage_scores',
        'a': 'a', 'b': 'b', 'output_key': 'study.d',
    })
    CohenDAcrossGroupsAnalyzer().analyze(study, cfg)
    d = study.get('study.d')
    assert d.shape == (3,)
    # Expect d > 0 on average since A has higher mean than B
    assert d.mean() > 0
    meta = study.get('study.d.meta')
    assert meta['n_a'] == 4 and meta['n_b'] == 4


def test_cohen_d_handles_no_subjects_with_key():
    a = _group('a', 'group_a')  # zero subjects with the key
    b = _group(
        'b', 'group_b',
        subject_arrays={'S0': np.array([1.0, 2.0])},
    )
    study = _study([a, b])
    cfg = _cfg('cohen_d_across_groups', {
        'input_key': 'analysis.fsaverage_scores',
        'a': 'a', 'b': 'b', 'output_key': 'study.d',
    })
    with pytest.raises(ValueError) as ei:
        CohenDAcrossGroupsAnalyzer().analyze(study, cfg)
    assert "no subjects in group 'a'" in str(ei.value)


def test_cohen_d_degenerate_zero_variance_returns_nan():
    """If both groups have identical-per-voxel values, pooled std=0 → NaN."""
    a = _group(
        'a', 'group_a',
        subject_arrays={f'S{i}': np.array([1.0, 1.0]) for i in range(3)},
    )
    b = _group(
        'b', 'group_b',
        subject_arrays={f'S{i}': np.array([1.0, 1.0]) for i in range(3)},
    )
    study = _study([a, b])
    cfg = _cfg('cohen_d_across_groups', {
        'input_key': 'analysis.fsaverage_scores',
        'a': 'a', 'b': 'b', 'output_key': 'study.d',
    })
    CohenDAcrossGroupsAnalyzer().analyze(study, cfg)
    d = study.get('study.d')
    assert np.all(np.isnan(d))


# ─── study_summary_html ────────────────────────────────────────


def test_study_summary_html_renders(tmp_path):
    """Smoke test: report writes a file containing the study name + groups."""
    from fmriflow.core.run_summary import StudyRunSummary

    g_a = _group('reading', 'group_reading',
                 artifacts={'group.scores_mean': np.zeros(10)})
    g_b = _group('listening', 'group_listening',
                 artifacts={'group.scores_mean': np.zeros(10)})
    study = _study([g_a, g_b])
    study.put('study.delta_r_minus_l', np.zeros(10, dtype=np.float32))
    study.study_summary = StudyRunSummary(
        study_name='demo_study',
        group_labels=['reading', 'listening'],
        started_at='2026-06-02T00:00:00Z',
        finished_at='2026-06-02T00:00:10Z',
        total_elapsed_s=10.0,
        run_id='studyrun_test',
    )

    StudySummaryHtmlReporter().report(
        study, {'output_dir': str(tmp_path),
                'study_report': [{'name': 'study_summary_html'}]},
    )

    out = tmp_path / 'study_summary.html'
    assert out.is_file()
    text = out.read_text()
    assert 'demo_study' in text
    assert 'reading' in text and 'listening' in text
    assert 'study.delta_r_minus_l' in text
    assert 'ndarray shape=(10,)' in text


# ─── registry ──────────────────────────────────────────────────


def test_builtin_study_plugins_registered():
    """All four built-ins should be picked up by ModuleRegistry."""
    from fmriflow.registry import ModuleRegistry
    r = ModuleRegistry()
    r.discover()
    modules = r.list_modules()
    assert 'group_delta' in modules['study_analyzers']
    assert 'cohen_d_across_groups' in modules['study_analyzers']
    assert 'study_summary_html' in modules['study_reporters']
    assert 'study_delta_flatmap' in modules['study_reporters']
