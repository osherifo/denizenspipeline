"""run-group / run-study --resume continue the most recent run directory."""

import os
from types import SimpleNamespace

from fmriflow.cli import _resume_run_id
from fmriflow.group_orchestrator import GroupOrchestrator, latest_run_id
from fmriflow.study_orchestrator import StudyOrchestrator


def test_latest_run_id_prefers_the_latest_symlink(tmp_path):
    (tmp_path / "20260101T000000Z").mkdir()
    (tmp_path / "20260202T000000Z").mkdir()
    os.symlink("20260101T000000Z", tmp_path / "latest", target_is_directory=True)
    assert latest_run_id(tmp_path) == "20260101T000000Z"


def test_latest_run_id_falls_back_to_the_newest_directory(tmp_path):
    (tmp_path / "20260101T000000Z").mkdir()
    (tmp_path / "20260202T000000Z").mkdir()
    assert latest_run_id(tmp_path) == "20260202T000000Z"


def test_latest_run_id_is_none_without_runs(tmp_path):
    assert latest_run_id(tmp_path / "missing") is None
    assert latest_run_id(tmp_path) is None


def test_group_and_study_resolve_from_output_dir(tmp_path):
    (tmp_path / "g" / "run_a").mkdir(parents=True)
    (tmp_path / "s" / "run_b").mkdir(parents=True)
    assert GroupOrchestrator.resolve_resume_run_id(
        {"group": "g", "output_dir": str(tmp_path / "g")}) == "run_a"
    assert StudyOrchestrator.resolve_resume_run_id(
        {"study": "s", "output_dir": str(tmp_path / "s")}) == "run_b"


def test_cli_run_id_selection(tmp_path):
    (tmp_path / "run_a").mkdir()
    cfg = {"group": "g", "output_dir": str(tmp_path)}
    resolve = GroupOrchestrator.resolve_resume_run_id
    assert _resume_run_id(SimpleNamespace(run_id=None, resume=True), resolve, cfg) == "run_a"
    assert _resume_run_id(SimpleNamespace(run_id=None, resume=False), resolve, cfg) is None
    assert _resume_run_id(SimpleNamespace(run_id="explicit", resume=True), resolve, cfg) == "explicit"
