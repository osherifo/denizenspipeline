"""Tests for the Phase 3 bidirectional flow.

Covers:
- ``stacked_weights_pca`` builds a SemanticSubspace by SVD on
  voxel-concatenated weight blocks
- ``project_to_subspace`` reads ``external.<binding>`` and writes the
  per-voxel projection
- The full GroupOrchestrator round-trip — group analyzer with
  ``produces_subject_artifact=True`` triggers a second pass that
  re-runs each subject with the group artifact bound in
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from fmriflow.context import PipelineContext
from fmriflow.core.group_types import GroupResult, SubjectResult
from fmriflow.core.run_summary import RunSummary, StageRecord
from fmriflow.core.types import ModelResult, SemanticSubspace
from fmriflow.group_orchestrator import GroupOrchestrator
from fmriflow.modules.analyzers.project_to_subspace import (
    ProjectToSubspaceAnalyzer,
)
from fmriflow.modules.group_analyzers.stacked_weights_pca import (
    StackedWeightsPCAAnalyzer,
)
from fmriflow.registry import ModuleRegistry


# ─── helpers ───────────────────────────────────────────────────

def _model_result(weights: np.ndarray, n_voxels: int) -> ModelResult:
    """Build a single-feature ModelResult for testing.

    Feature 'english1000' with `feature_dim` and `n_delays` derived from
    `weights.shape[0]`. The convention: one feature with `fdim*n_delays`
    delayed rows.
    """
    return ModelResult(
        weights=weights,
        scores=np.zeros(n_voxels, dtype=np.float32),
        alphas=np.zeros(n_voxels, dtype=np.float32),
        feature_names=['english1000'],
        feature_dims=[weights.shape[0]],   # treat as 1 delay × fdim rows
        delays=[1],
    )


def _make_subject(subject: str, weights: np.ndarray,
                  n_voxels: int) -> SubjectResult:
    ctx = PipelineContext({'subject': subject})
    ctx.put('result', _model_result(weights, n_voxels))
    now = datetime.now(timezone.utc).isoformat()
    return SubjectResult(
        subject=subject, experiment='demo',
        run_dir=Path('/tmp/stub') / subject,
        run_summary=RunSummary(
            experiment='demo', subject=subject,
            started_at=now, finished_at=now, total_elapsed_s=0.01,
            stages=[StageRecord(name='model', status='ok',
                                elapsed_s=0.01, detail='ok')],
            config_snapshot={'subject': subject},
        ),
        context=ctx,
    )


# ─── stacked_weights_pca ──────────────────────────────────────

def test_stacked_weights_pca_builds_subspace():
    rng = np.random.default_rng(0)
    # Each subject: 985 delayed weights × n_voxels_subject
    g = GroupResult(group_name='demo')
    g.subjects = [
        _make_subject('S1', rng.standard_normal((10, 50)), 50),
        _make_subject('S2', rng.standard_normal((10, 60)), 60),
        _make_subject('S3', rng.standard_normal((10, 40)), 40),
    ]
    analyzer = StackedWeightsPCAAnalyzer()
    analyzer.analyze(g, {'group_analyze': [{
        'name': 'stacked_weights_pca',
        'params': {'feature': 'english1000', 'n_components': 5,
                   'output_key': 'group.basis'},
    }]})

    basis = g.get('group.basis')
    assert isinstance(basis, SemanticSubspace)
    assert basis.basis.shape == (10, 5)
    assert basis.singular_values.shape == (5,)
    assert basis.feature == 'english1000'
    # Basis columns should be unit-norm (SVD U is orthonormal)
    norms = np.linalg.norm(basis.basis, axis=0)
    np.testing.assert_allclose(norms, np.ones(5), atol=1e-10)
    # Singular values descending
    assert np.all(np.diff(basis.singular_values) <= 0)


def test_stacked_weights_pca_subject_bindings():
    rng = np.random.default_rng(1)
    g = GroupResult(group_name='demo')
    g.subjects = [
        _make_subject('S1', rng.standard_normal((10, 30)), 30),
        _make_subject('S2', rng.standard_normal((10, 30)), 30),
    ]
    analyzer = StackedWeightsPCAAnalyzer()
    analyzer.analyze(g, {'group_analyze': [{
        'name': 'stacked_weights_pca',
        'params': {'feature': 'english1000', 'n_components': 3,
                   'output_key': 'group.basis',
                   'binding_name': 'sem_basis'},
    }]})

    bindings = analyzer.subject_bindings(g)
    assert 'sem_basis' in bindings
    assert isinstance(bindings['sem_basis'], SemanticSubspace)


def test_stacked_weights_pca_rejects_inconsistent_rows():
    rng = np.random.default_rng(2)
    g = GroupResult(group_name='demo')
    g.subjects = [_make_subject('S1', rng.standard_normal((10, 20)), 20)]
    # Manually corrupt S2 — different number of delayed rows
    s2 = _make_subject('S2', rng.standard_normal((12, 20)), 20)
    g.subjects.append(s2)
    with pytest.raises(ValueError, match='delayed rows'):
        StackedWeightsPCAAnalyzer().analyze(g, {'group_analyze': [{
            'name': 'stacked_weights_pca',
            'params': {'feature': 'english1000', 'n_components': 3},
        }]})


def test_stacked_weights_pca_requires_feature_param():
    errors = StackedWeightsPCAAnalyzer().validate_config({'group_analyze': [{
        'name': 'stacked_weights_pca',
        'params': {},
    }]})
    assert errors and 'feature' in errors[0]


# ─── project_to_subspace ──────────────────────────────────────

def test_project_to_subspace_writes_projection():
    rng = np.random.default_rng(3)
    basis_mat = np.eye(10)[:, :3].astype(np.float64)    # identity-like
    basis = SemanticSubspace(
        basis=basis_mat,
        singular_values=np.array([3.0, 2.0, 1.0]),
        feature='english1000', n_delays=1, feature_dim=10,
    )
    weights = rng.standard_normal((10, 25))
    ctx = PipelineContext({'subject': 'S1'})
    ctx.put('result', _model_result(weights, 25))
    ctx.put('external.semantic_pca_basis', basis)

    ProjectToSubspaceAnalyzer().analyze(ctx, {'analysis': [{
        'name': 'project_to_subspace', 'params': {},
    }]})

    proj = ctx.get('analysis.semantic_pc_projection')
    assert proj.shape == (3, 25)
    # With identity-like basis, projection should equal the first 3 rows.
    np.testing.assert_allclose(proj, weights[:3, :])


def test_project_to_subspace_no_op_when_binding_missing(caplog):
    weights = np.random.default_rng(4).standard_normal((10, 20))
    ctx = PipelineContext({'subject': 'S1'})
    ctx.put('result', _model_result(weights, 20))
    # No external.* key — analyzer should warn and exit, not crash.
    ProjectToSubspaceAnalyzer().analyze(ctx, {'analysis': []})
    assert not ctx.has('analysis.semantic_pc_projection')


def test_project_to_subspace_custom_binding_and_output():
    rng = np.random.default_rng(5)
    basis_mat = np.eye(10)[:, :2].astype(np.float64)
    basis = SemanticSubspace(
        basis=basis_mat,
        singular_values=np.array([2.0, 1.0]),
        feature='english1000', n_delays=1, feature_dim=10,
    )
    weights = rng.standard_normal((10, 15))
    ctx = PipelineContext({'subject': 'S1'})
    ctx.put('result', _model_result(weights, 15))
    ctx.put('external.sem_basis', basis)

    ProjectToSubspaceAnalyzer().analyze(ctx, {'analysis': [{
        'name': 'project_to_subspace',
        'params': {'binding': 'sem_basis', 'output_key': 'analysis.proj'},
    }]})
    assert ctx.has('analysis.proj')
    assert not ctx.has('analysis.semantic_pc_projection')


# ─── orchestrator second-pass round-trip ─────────────────────

def _valid_template() -> dict:
    return {
        'experiment': 'demo',
        'stimulus': {'loader': 'textgrid'},
        'response': {'loader': 'cloud'},
        'features': [{'name': 'english1000'}],
        'split': {'test_runs': ['story01']},
        'analysis': [{
            'name': 'project_to_subspace',
            'params': {'binding': 'sem_basis',
                       'output_key': 'analysis.proj'},
        }],
    }


def test_orchestrator_runs_bidirectional_round_trip(tmp_path, monkeypatch):
    """End-to-end: group analyzer with produces_subject_artifact=True
    drives the second pass with the binding actually arriving in
    subject contexts."""
    import fmriflow.group_orchestrator as go

    rng = np.random.default_rng(7)
    n_rows = 10
    voxel_counts = {'S1': 50, 'S2': 60, 'S3': 40}
    second_pass_calls: list[tuple[str, list[str], bool]] = []

    class _StubOrch:
        def __init__(self, config, registry):
            self.config = config
            self.registry = registry
            self.ctx: PipelineContext | None = None

        def run(self, stages=None, context=None):
            subject = self.config['subject']
            if context is None:
                # First pass — build a fresh context with a ModelResult
                ctx = PipelineContext(self.config)
                nvox = voxel_counts[subject]
                ctx.put('result', _model_result(
                    rng.standard_normal((n_rows, nvox)), nvox))
                now = datetime.now(timezone.utc).isoformat()
                ctx.run_summary = RunSummary(
                    experiment='demo', subject=subject,
                    started_at=now, finished_at=now, total_elapsed_s=0.01,
                    stages=[StageRecord(name='model', status='ok',
                                        elapsed_s=0.01, detail='ok')],
                    config_snapshot=dict(self.config),
                )
                self.ctx = ctx
            else:
                # Second pass — drive the project_to_subspace analyzer
                second_pass_calls.append(
                    (subject, list(stages or []),
                     context.has('external.sem_basis')))
                ProjectToSubspaceAnalyzer().analyze(context, self.config)
                self.ctx = context
            return self.ctx

    monkeypatch.setattr(go, 'PipelineOrchestrator', _StubOrch)

    cfg = {
        'group': 'demo_group',
        'subjects': ['S1', 'S2', 'S3'],
        'subject_template': _valid_template(),
        'output_dir': str(tmp_path),
        'group_analyze': [{
            'name': 'stacked_weights_pca',
            'params': {'feature': 'english1000', 'n_components': 3,
                       'output_key': 'group.basis',
                       'binding_name': 'sem_basis'},
        }],
    }
    registry = ModuleRegistry()
    registry.discover()
    orch = GroupOrchestrator(cfg, registry)
    result = orch.run()

    # Group analyzer produced the basis.
    basis = result.get('group.basis')
    assert isinstance(basis, SemanticSubspace)
    assert basis.feature == 'english1000'

    # Second pass ran once per subject, each with the binding present.
    assert sorted(c[0] for c in second_pass_calls) == ['S1', 'S2', 'S3']
    for subject, stages, has_binding in second_pass_calls:
        assert stages == ['analyze', 'report']
        assert has_binding, f"{subject} did not see external.sem_basis"

    # Each subject's context now has the projection.
    for sr in result.subjects:
        proj = sr.context.get('analysis.proj')
        assert proj.shape[0] == 3
        assert proj.shape[1] == voxel_counts[sr.subject]
