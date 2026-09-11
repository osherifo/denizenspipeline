"""Group runs report subjects that cannot contribute, and persist second-pass records."""

from datetime import datetime, timezone

from fmriflow.context import PipelineContext
from fmriflow.core.run_summary import RunSummary, StageRecord
from fmriflow.group_orchestrator import GroupOrchestrator
from fmriflow.modules._decorators import _group_analyzers
from fmriflow.registry import ModuleRegistry
from tests.test_integration.test_group_orchestrator import (
    _fake_run,
    _group_cfg,
    _patch_pipeline_run,
)


def _now():
    return datetime.now(timezone.utc).isoformat()


class _NoopGroupAnalyzer:
    name = "zz_noop_group"
    produces_subject_artifact = False

    def analyze(self, group, config):
        return None

    def subject_bindings(self, group):
        return {}

    def validate_config(self, config):
        return []


class _BindingGroupAnalyzer(_NoopGroupAnalyzer):
    name = "zz_binding_group"
    produces_subject_artifact = True

    def subject_bindings(self, group):
        return {"basis": 1}


def test_subjects_resumed_from_disk_mark_group_analyze_warning(tmp_path, monkeypatch):
    s1_dir = tmp_path / "resume_run" / "subjects" / "S1"
    s1_dir.mkdir(parents=True)
    RunSummary(
        experiment="demo", subject="S1", started_at=_now(), finished_at=_now(),
        total_elapsed_s=0.01,
        stages=[StageRecord(name="stimuli", status="ok", elapsed_s=0.01, detail="ok")],
        config_snapshot={},
    ).save_json(s1_dir / "run_summary.json")
    _patch_pipeline_run(monkeypatch)
    _group_analyzers["zz_noop_group"] = _NoopGroupAnalyzer
    try:
        cfg = _group_cfg(tmp_path, group_analyze=[{"name": "zz_noop_group"}])
        orch = GroupOrchestrator(cfg, ModuleRegistry(), run_id="resume_run")
        orch.run(resume=True)
    finally:
        _group_analyzers.pop("zz_noop_group", None)

    stage = next(s for s in orch._stage_records if s.name == "group_analyze")
    assert stage.status == "warning"
    assert stage.nodes[0].status == "warning"
    assert "S1" in stage.nodes[0].detail


def test_second_pass_records_are_saved_to_subject_summary(tmp_path, monkeypatch):
    import fmriflow.analysis.scope_runners as runners

    def _first_pass(config):
        ctx = _fake_run(config)
        ctx.run_summary.stages = [
            StageRecord(name="model", status="ok", elapsed_s=0.01, detail="fit"),
            StageRecord(name="analyze", status="ok", elapsed_s=0.01, detail="first"),
        ]
        return ctx

    def _second_pass(config, catalog, stages, context, **kwargs):
        # like a partial run: the summary is replaced by one holding only the stages that just ran
        context.run_summary = RunSummary(
            experiment="demo", subject=config["subject"],
            started_at=_now(), finished_at=_now(), total_elapsed_s=0.02,
            stages=[StageRecord(name="analyze", status="ok", elapsed_s=0.01, detail="projected"),
                    StageRecord(name="report", status="ok", elapsed_s=0.01, detail="1 artifact")],
            config_snapshot=dict(config),
        )
        return context

    _patch_pipeline_run(monkeypatch, behaviour=_first_pass)
    monkeypatch.setattr(runners, "run_subject_stages", _second_pass)
    _group_analyzers["zz_binding_group"] = _BindingGroupAnalyzer
    try:
        cfg = _group_cfg(tmp_path, group_analyze=[{"name": "zz_binding_group"}])
        result = GroupOrchestrator(cfg, ModuleRegistry(), run_id="second_pass").run()
    finally:
        _group_analyzers.pop("zz_binding_group", None)

    for sr in result.subjects:
        on_disk = RunSummary.from_json(sr.run_dir / "run_summary.json")
        by_name = {s.name: s for s in on_disk.stages}
        assert [s.name for s in on_disk.stages] == ["model", "analyze", "report"]
        assert by_name["analyze"].detail == "second pass: projected"
        assert by_name["report"].detail == "second pass: 1 artifact"
        assert isinstance(sr.context, PipelineContext)
        assert sr.context.run_summary is sr.run_summary
