"""Tests for the Phase 1 group orchestrator skeleton.

Covers:
- ``validate_group_config`` rejects malformed group configs
- ``GroupOrchestrator._build_subject_configs`` deep-merges
  ``subject_overrides`` over ``subject_template`` and pins output_dirs
- ``GroupOrchestrator.run`` fans out to ``PipelineOrchestrator`` per
  subject and writes ``group_summary.json``
- ``--resume`` semantics skip subjects whose ``run_summary.json`` is ok
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from fmriflow.config.schema import validate_group_config
from fmriflow.context import PipelineContext
from fmriflow.core.run_summary import RunSummary, StageRecord
from fmriflow.exceptions import ConfigError
from fmriflow.group_orchestrator import GroupOrchestrator
from fmriflow.registry import ModuleRegistry


# ─── helpers ───────────────────────────────────────────────────

def _valid_template() -> dict:
    return {
        'experiment': 'demo',
        'stimulus': {'loader': 'textgrid'},
        'response': {'loader': 'cloud'},
        'features': [{'name': 'numwords'}],
        'split': {'test_runs': ['story01']},
    }


def _group_cfg(tmp_path: Path, **extra) -> dict:
    base = {
        'group': 'demo_group',
        'subjects': ['S1', 'S2', 'S3'],
        'subject_template': _valid_template(),
        'output_dir': str(tmp_path),
    }
    base.update(extra)
    return base


def _fake_run(subject_config: dict) -> PipelineContext:
    """Stand-in for PipelineOrchestrator.run — returns a ctx with summary."""
    ctx = PipelineContext(subject_config)
    now = datetime.now(timezone.utc).isoformat()
    ctx.run_summary = RunSummary(
        experiment=subject_config.get('experiment', ''),
        subject=subject_config['subject'],
        started_at=now,
        finished_at=now,
        total_elapsed_s=0.01,
        stages=[StageRecord(name='stimuli', status='ok',
                            elapsed_s=0.01, detail='3 runs')],
        config_snapshot=dict(subject_config),
    )
    return ctx


# ─── validate_group_config ─────────────────────────────────────

def test_validate_group_config_accepts_valid(tmp_path):
    errors = validate_group_config(_group_cfg(tmp_path))
    assert errors == []


def test_validate_group_config_requires_group_name(tmp_path):
    cfg = _group_cfg(tmp_path)
    del cfg['group']
    errors = validate_group_config(cfg)
    assert any("'group'" in e for e in errors)


def test_validate_group_config_requires_subjects(tmp_path):
    cfg = _group_cfg(tmp_path)
    del cfg['subjects']
    errors = validate_group_config(cfg)
    assert any('subjects' in e for e in errors)


def test_validate_group_config_requires_template(tmp_path):
    cfg = _group_cfg(tmp_path)
    del cfg['subject_template']
    errors = validate_group_config(cfg)
    assert any('subject_template' in e for e in errors)


def test_validate_group_config_overrides_must_be_dict(tmp_path):
    cfg = _group_cfg(tmp_path, subject_overrides=['not-a-dict'])
    errors = validate_group_config(cfg)
    assert any('subject_overrides' in e for e in errors)


def test_validate_group_config_group_analyze_must_be_list(tmp_path):
    cfg = _group_cfg(tmp_path, group_analyze={'name': 'oops'})
    errors = validate_group_config(cfg)
    assert any('group_analyze' in e for e in errors)


# ─── subject config building ───────────────────────────────────

def test_build_subject_configs_deep_merge(tmp_path):
    cfg = _group_cfg(tmp_path, subject_overrides={
        'S2': {
            'response': {'mask': 'custom_mask_S2.nii'},
            'features': [{'name': 'english1000'}],
        },
    })
    orch = GroupOrchestrator(cfg, ModuleRegistry())
    subject_configs = orch._build_subject_configs()

    by_sub = {c['subject']: c for c in subject_configs}

    # S1 unchanged
    assert by_sub['S1']['response']['loader'] == 'cloud'
    assert 'mask' not in by_sub['S1'].get('response', {})

    # S2 deep-merged: response.loader kept from template, mask added
    assert by_sub['S2']['response']['loader'] == 'cloud'
    assert by_sub['S2']['response']['mask'] == 'custom_mask_S2.nii'

    # Features list is replaced (not merged element-wise — same as
    # merge_configs's behaviour for non-dict values)
    assert by_sub['S2']['features'] == [{'name': 'english1000'}]

    # output_dir is pinned under <group_dir>/subjects/<subject>
    for sub, c in by_sub.items():
        assert c['reporting']['output_dir'].endswith(f'subjects/{sub}')


def test_build_subject_configs_missing_template_required_field(tmp_path):
    bad_template = _valid_template()
    del bad_template['experiment']     # required by validate_config
    cfg = _group_cfg(tmp_path, subject_template=bad_template)
    orch = GroupOrchestrator(cfg, ModuleRegistry())
    with pytest.raises(ConfigError):
        orch._build_subject_configs()


def test_build_subject_configs_missing_subjects(tmp_path):
    cfg = _group_cfg(tmp_path)
    del cfg['subjects']
    orch = GroupOrchestrator(cfg, ModuleRegistry())
    with pytest.raises(ConfigError):
        orch._build_subject_configs()


# ─── fan-out ──────────────────────────────────────────────────

def _patch_pipeline_run(monkeypatch, behaviour=_fake_run):
    """Stub out PipelineOrchestrator.run inside group_orchestrator."""
    import fmriflow.group_orchestrator as go

    class _StubOrch:
        def __init__(self, config, registry):
            self.config = config
            self.registry = registry
            self.ctx = None

        def run(self, stages=None, context=None):
            self.ctx = behaviour(self.config)
            return self.ctx

    monkeypatch.setattr(go, 'PipelineOrchestrator', _StubOrch)


def test_group_run_fans_out_and_writes_summary(tmp_path, monkeypatch):
    _patch_pipeline_run(monkeypatch)
    cfg = _group_cfg(tmp_path)
    orch = GroupOrchestrator(cfg, ModuleRegistry())

    result = orch.run()

    assert len(result.subjects) == 3
    assert {sr.subject for sr in result.subjects} == {'S1', 'S2', 'S3'}
    for sr in result.subjects:
        assert sr.status == 'ok'
        assert (sr.run_dir / 'run_summary.json').is_file()

    group_summary = tmp_path / 'group_summary.json'
    assert group_summary.is_file()
    assert result.group_summary is not None
    assert result.group_summary.group_name == 'demo_group'
    # one record per group stage that ran (collect, fanout)
    stage_names = {s.name for s in result.group_summary.group_stages}
    assert 'group_collect' in stage_names
    assert 'subject_fanout' in stage_names


def test_group_run_records_failure(tmp_path, monkeypatch):
    def _fail_for_s2(scfg):
        if scfg['subject'] == 'S2':
            raise RuntimeError("boom")
        return _fake_run(scfg)

    _patch_pipeline_run(monkeypatch, behaviour=_fail_for_s2)
    cfg = _group_cfg(tmp_path)
    orch = GroupOrchestrator(cfg, ModuleRegistry())
    result = orch.run()

    # All three SubjectResults are present even though S2 failed.
    assert len(result.subjects) == 3
    by_sub = {sr.subject: sr for sr in result.subjects}
    assert by_sub['S1'].status == 'ok'
    assert by_sub['S3'].status == 'ok'
    # S2 has no stages recorded (the stub raised before any stage ran)
    # so the run_summary is empty — surfaces as 'unknown'.
    assert by_sub['S2'].status == 'unknown'


# ─── resume ────────────────────────────────────────────────────

def test_resume_skips_already_ok_subjects(tmp_path, monkeypatch):
    # Pre-create a successful run for S1.
    s1_dir = tmp_path / 'subjects' / 'S1'
    s1_dir.mkdir(parents=True)
    now = datetime.now(timezone.utc).isoformat()
    RunSummary(
        experiment='demo', subject='S1',
        started_at=now, finished_at=now, total_elapsed_s=0.01,
        stages=[StageRecord(name='stimuli', status='ok',
                            elapsed_s=0.01, detail='3 runs')],
        config_snapshot={},
    ).save_json(s1_dir / 'run_summary.json')

    calls = []

    def _track(scfg):
        calls.append(scfg['subject'])
        return _fake_run(scfg)

    _patch_pipeline_run(monkeypatch, behaviour=_track)
    cfg = _group_cfg(tmp_path)
    orch = GroupOrchestrator(cfg, ModuleRegistry())
    result = orch.run(resume=True)

    # S1 was skipped; only S2 and S3 actually ran the pipeline stub.
    assert sorted(calls) == ['S2', 'S3']
    # But S1 still appears in the result, loaded from disk.
    assert {sr.subject for sr in result.subjects} == {'S1', 'S2', 'S3'}
    s1 = next(sr for sr in result.subjects if sr.subject == 'S1')
    assert s1.context is None
    assert s1.status == 'ok'
