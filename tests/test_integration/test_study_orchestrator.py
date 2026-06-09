"""Tests for the Phase 1 study orchestrator skeleton.

Covers:
- ``validate_study_config`` rejects malformed study configs
- ``StudyOrchestrator._collect_groups`` validates the ``groups:`` block
  (unique labels, missing config paths, missing top-level ``group:``)
- ``StudyOrchestrator.run`` fans out to ``GroupOrchestrator`` per group
  and writes ``study_summary.json``
- The on-disk layout (``<study_dir>/<run_id>/`` + ``latest`` symlink
  + nested ``groups/<label>/<group_run_id>/``)
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from fmriflow.config.schema import validate_study_config
from fmriflow.core.group_types import GroupResult, SubjectResult
from fmriflow.core.run_summary import (
    GroupRunSummary, RunSummary, StageRecord, StudyRunSummary,
)
from fmriflow.exceptions import ConfigError
from fmriflow.registry import ModuleRegistry
from fmriflow.study_orchestrator import StudyOrchestrator


# ─── helpers ───────────────────────────────────────────────────

def _valid_group_yaml() -> dict:
    return {
        'group': 'group_a',
        'subjects': ['S1', 'S2'],
        'subject_template': {
            'experiment': 'demo',
            'stimulus': {'loader': 'textgrid'},
            'response': {'loader': 'cloud'},
            'features': [{'name': 'numwords'}],
            'split': {'test_runs': ['story01']},
        },
    }


def _study_cfg(tmp_path: Path, *, groups: list[dict] | None = None,
               **extra) -> dict:
    """Build a valid study YAML pointing at on-disk group configs."""
    if groups is None:
        # Two distinct group YAMLs written next to the tmp_path.
        groups = []
        for label, gname in [('reading', 'group_reading'),
                             ('listening', 'group_listening')]:
            g = _valid_group_yaml()
            g['group'] = gname
            p = tmp_path / f'{label}.yaml'
            with open(p, 'w') as f:
                yaml.safe_dump(g, f)
            groups.append({'name': label, 'config': str(p)})
    base = {
        'study': 'demo_study',
        'groups': groups,
        'output_dir': str(tmp_path / 'out'),
    }
    base.update(extra)
    return base


def _fake_group_result(label: str, group_name: str,
                       run_dir: Path) -> GroupResult:
    """A pre-built GroupResult matching what a successful run would
    produce — used by the GroupOrchestrator stub below."""
    now = datetime.now(timezone.utc).isoformat()
    summary = GroupRunSummary(
        group_name=group_name,
        subjects=['S1', 'S2'],
        started_at=now, finished_at=now, total_elapsed_s=0.01,
        subject_summaries=[
            RunSummary(
                experiment='demo', subject='S1',
                started_at=now, finished_at=now, total_elapsed_s=0.005,
                stages=[StageRecord(name='stimuli', status='ok',
                                    elapsed_s=0.005, detail='2 runs')],
                config_snapshot={},
            ),
            RunSummary(
                experiment='demo', subject='S2',
                started_at=now, finished_at=now, total_elapsed_s=0.005,
                stages=[StageRecord(name='stimuli', status='ok',
                                    elapsed_s=0.005, detail='2 runs')],
                config_snapshot={},
            ),
        ],
        group_stages=[
            StageRecord(name='group_collect', status='ok',
                        elapsed_s=0.0, detail=''),
            StageRecord(name='subject_fanout', status='ok',
                        elapsed_s=0.01, detail=''),
        ],
        config_snapshot={},
        run_id=f"stubrun__{label}",
    )
    return GroupResult(
        group_name=group_name,
        subjects=[
            SubjectResult(
                subject=s.subject, experiment='demo',
                run_dir=run_dir, run_summary=s,
            )
            for s in summary.subject_summaries
        ],
        group_summary=summary,
    )


def _patch_group_orch(monkeypatch, *, fail_for: set[str] | None = None):
    """Stub out GroupOrchestrator inside study_orchestrator."""
    import fmriflow.study_orchestrator as so

    class _StubGroupOrch:
        def __init__(self, config, registry, run_id=None):
            self.config = config
            self.registry = registry
            self.run_id = run_id or 'stubrun'
            self.group_name = config.get('group') or 'unknown'
            self.group_dir = Path(config.get('output_dir', '.')) / self.run_id
            self.group_dir.mkdir(parents=True, exist_ok=True)
            self.group: GroupResult = _fake_group_result(
                label=self.run_id, group_name=self.group_name,
                run_dir=self.group_dir,
            )

        def run(self, resume: bool = False) -> GroupResult:
            if fail_for and self.group_name in fail_for:
                raise RuntimeError(f"group {self.group_name} boom")
            return self.group

    monkeypatch.setattr(so, 'GroupOrchestrator', _StubGroupOrch)


# ─── validate_study_config ─────────────────────────────────────

def test_validate_study_config_accepts_valid(tmp_path):
    errors = validate_study_config(_study_cfg(tmp_path))
    assert errors == []


def test_validate_study_config_requires_study_name(tmp_path):
    cfg = _study_cfg(tmp_path)
    del cfg['study']
    errors = validate_study_config(cfg)
    assert any("'study'" in e for e in errors)


def test_validate_study_config_requires_groups(tmp_path):
    cfg = _study_cfg(tmp_path, groups=[])
    errors = validate_study_config(cfg)
    assert any("'groups'" in e for e in errors)


def test_validate_study_config_rejects_duplicate_labels(tmp_path):
    g = _valid_group_yaml()
    p = tmp_path / 'x.yaml'
    with open(p, 'w') as f:
        yaml.safe_dump(g, f)
    cfg = _study_cfg(tmp_path, groups=[
        {'name': 'reading', 'config': str(p)},
        {'name': 'reading', 'config': str(p)},
    ])
    errors = validate_study_config(cfg)
    assert any("duplicate label 'reading'" in e for e in errors)


def test_validate_study_config_rejects_missing_config_path(tmp_path):
    cfg = _study_cfg(tmp_path, groups=[{'name': 'reading'}])
    errors = validate_study_config(cfg)
    assert any("missing 'config:'" in e for e in errors)


def test_validate_study_config_rejects_bad_study_analyze(tmp_path):
    cfg = _study_cfg(tmp_path, study_analyze=[{'no_name_key': True}])
    errors = validate_study_config(cfg)
    assert any("missing 'name'" in e for e in errors)


# ─── _collect_groups (deep validation) ────────────────────────

def test_collect_rejects_unique_labels_at_runtime(tmp_path, monkeypatch):
    # validator catches this too, but the orchestrator's own check is
    # the last line of defence (e.g. for configs built programmatically).
    g = _valid_group_yaml()
    p = tmp_path / 'x.yaml'
    with open(p, 'w') as f:
        yaml.safe_dump(g, f)
    cfg = {
        'study': 'demo',
        'groups': [
            {'name': 'a', 'config': str(p)},
            {'name': 'a', 'config': str(p)},
        ],
        'output_dir': str(tmp_path / 'out'),
    }
    orch = StudyOrchestrator(cfg, ModuleRegistry(), run_id='t')
    with pytest.raises(ConfigError) as ei:
        orch._collect_groups()
    msg = "; ".join(ei.value.args[0]) if isinstance(ei.value.args[0], list) else str(ei.value)
    assert "duplicate label 'a'" in msg


def test_collect_rejects_missing_referenced_yaml(tmp_path):
    cfg = {
        'study': 'demo',
        'groups': [{'name': 'a', 'config': str(tmp_path / 'nope.yaml')}],
        'output_dir': str(tmp_path / 'out'),
    }
    orch = StudyOrchestrator(cfg, ModuleRegistry(), run_id='t')
    with pytest.raises(ConfigError) as ei:
        orch._collect_groups()
    msg = "; ".join(ei.value.args[0]) if isinstance(ei.value.args[0], list) else str(ei.value)
    assert "config file not found" in msg


def test_collect_rejects_non_group_yaml(tmp_path):
    # Subject YAML (no top-level group:) — should be rejected.
    p = tmp_path / 'subject.yaml'
    with open(p, 'w') as f:
        yaml.safe_dump({'experiment': 'x', 'subject': 'S1'}, f)
    cfg = {
        'study': 'demo',
        'groups': [{'name': 'a', 'config': str(p)}],
        'output_dir': str(tmp_path / 'out'),
    }
    orch = StudyOrchestrator(cfg, ModuleRegistry(), run_id='t')
    with pytest.raises(ConfigError) as ei:
        orch._collect_groups()
    msg = "; ".join(ei.value.args[0]) if isinstance(ei.value.args[0], list) else str(ei.value)
    assert "lacks top-level 'group:'" in msg


# ─── fan-out ───────────────────────────────────────────────────

def test_study_run_fans_out_and_writes_summary(tmp_path, monkeypatch):
    _patch_group_orch(monkeypatch)
    cfg = _study_cfg(tmp_path)
    orch = StudyOrchestrator(cfg, ModuleRegistry(), run_id='studyrun01')

    result = orch.run()

    # Two groups, both ok
    assert len(result.groups) == 2
    assert {g.study_label for g in result.groups} == {'reading', 'listening'}

    # Output lives in a timestamped subdirectory under output_dir.
    run_dir = Path(cfg['output_dir']) / 'studyrun01'
    assert run_dir.is_dir()
    assert (run_dir / 'study_summary.json').is_file()
    assert (run_dir / 'study.log').is_file()

    # 'latest' symlink points at this run.
    latest = Path(cfg['output_dir']) / 'latest'
    if latest.is_symlink():
        assert latest.resolve() == run_dir.resolve()

    # study_summary.json round-trips and carries the right shape.
    srs = StudyRunSummary.from_json(run_dir / 'study_summary.json')
    assert srs.study_name == 'demo_study'
    assert srs.run_id == 'studyrun01'
    assert srs.group_labels == ['reading', 'listening']
    stage_names = {s.name for s in srs.study_stages}
    assert 'study_collect' in stage_names
    assert 'groups_fanout' in stage_names

    # No study_analyze / study_report stages were declared, so they
    # shouldn't appear in study_stages.
    assert 'study_analyze' not in stage_names
    assert 'study_report' not in stage_names


def test_study_run_records_group_failure(tmp_path, monkeypatch):
    _patch_group_orch(monkeypatch, fail_for={'group_listening'})
    cfg = _study_cfg(tmp_path)
    orch = StudyOrchestrator(cfg, ModuleRegistry(), run_id='studyrun02')

    result = orch.run()
    # Both groups returned — failed one with the partial-result fallback
    # carries the study_label set to 'listening'.
    labels = {g.study_label for g in result.groups}
    assert labels == {'reading', 'listening'}
    # Summary persisted even with one failed group.
    run_dir = Path(cfg['output_dir']) / 'studyrun02'
    assert (run_dir / 'study_summary.json').is_file()


def test_study_run_resolves_default_output_dir(tmp_path, monkeypatch):
    """Without explicit output_dir, paths.study_runs_root() is used."""
    _patch_group_orch(monkeypatch)
    # Point study_runs_root at a tmp dir.
    import fmriflow.core.paths as paths
    monkeypatch.setattr(paths, 'home', lambda: tmp_path)

    cfg = _study_cfg(tmp_path)
    del cfg['output_dir']
    orch = StudyOrchestrator(cfg, ModuleRegistry(), run_id='studyrun03')
    orch.run()

    expected_root = tmp_path / 'study_runs' / 'demo_study' / 'studyrun03'
    assert (expected_root / 'study_summary.json').is_file()
