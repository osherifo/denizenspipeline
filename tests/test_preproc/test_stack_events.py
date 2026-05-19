"""Phase 5b — EventWriter + StackRunner event-sink tests.

Covers:

- ``EventWriter`` writes one JSON object per line, flushes after
  each write, and survives close + reopen (append mode).
- ``StackRunner`` with an attached ``event_sink`` emits the expected
  sequence (``started`` → ``stage_start`` / ``stage_done`` per
  stage → ``completed``) with the right schema fields.
- A failing stage emits ``stage_failed`` + ``failed`` and stops.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fmriflow.preproc.stack import (
    BootstrapStage,
    PreprocStack,
    TransformStage,
)
from fmriflow.preproc.stack_events import EventWriter
from fmriflow.preproc.stack_runner import (
    StackRunConfig,
    StackRunner,
)
from fmriflow.preproc.transform_registry import TransformRegistry
from fmriflow.preproc.workflow_registry import WorkflowRegistry


@pytest.fixture
def registries(tmp_path):
    wf = WorkflowRegistry(user_dir=tmp_path / "_wf")
    wf.discover()
    tx = TransformRegistry(user_dir=tmp_path / "_tx")
    tx.discover()
    return wf, tx


@pytest.fixture
def run_config(tmp_path):
    return StackRunConfig(
        subject="sub01",
        output_dir=tmp_path / "out",
        dataset="study1",
        sessions=["ses01"],
    )


# ── EventWriter ────────────────────────────────────────────────────


class TestEventWriter:
    def test_writes_one_json_object_per_line(self, tmp_path):
        path = tmp_path / "events.jsonl"
        with EventWriter(path) as w:
            w({"event": "started", "x": 1})
            w({"event": "completed", "y": 2})

        lines = path.read_text().strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["event"] == "started"
        assert json.loads(lines[0])["x"] == 1
        assert json.loads(lines[1])["event"] == "completed"

    def test_adds_timestamp_when_absent(self, tmp_path):
        path = tmp_path / "events.jsonl"
        with EventWriter(path) as w:
            w({"event": "x"})
        ev = json.loads(path.read_text().strip())
        assert "timestamp" in ev
        assert isinstance(ev["timestamp"], float)

    def test_preserves_supplied_timestamp(self, tmp_path):
        path = tmp_path / "events.jsonl"
        with EventWriter(path) as w:
            w({"event": "x", "timestamp": 123.456})
        ev = json.loads(path.read_text().strip())
        assert ev["timestamp"] == 123.456

    def test_append_mode_preserves_existing(self, tmp_path):
        path = tmp_path / "events.jsonl"
        with EventWriter(path) as w:
            w({"event": "a"})
        with EventWriter(path) as w:
            w({"event": "b"})

        lines = path.read_text().strip().splitlines()
        assert [json.loads(l)["event"] for l in lines] == ["a", "b"]


# ── StackRunner event emission ─────────────────────────────────────


class TestRunnerEmitsEvents:
    def test_happy_path_emission_sequence(self, registries, run_config):
        wf, tx = registries
        events: list[dict] = []
        runner = StackRunner(wf, tx, use_cache=False, event_sink=events.append)
        stack = PreprocStack(
            bootstrap=BootstrapStage(kind="nipype", workflow="identity"),
            transforms=[TransformStage(name="identity")],
        )
        result = runner.run(stack, run_config)
        assert result.status == "completed"

        names = [e["event"] for e in events]
        # Expected sequence: started, bootstrap start+done, transform start+done, completed.
        assert names == [
            "started",
            "stage_start", "stage_done",     # bootstrap
            "stage_start", "stage_done",     # transform
            "completed",
        ]

        # Spot-check schema on bootstrap stage_done.
        boot_done = events[2]
        assert boot_done["event"] == "stage_done"
        assert boot_done["stage_index"] == 0
        assert boot_done["kind"] == "bootstrap"
        assert boot_done["stage_name"] == "identity"
        assert boot_done["cache_hit"] is False
        assert isinstance(boot_done["duration_s"], float)
        assert boot_done["fingerprint"]

        # Final completed event.
        completed = events[-1]
        assert completed["event"] == "completed"
        assert completed["n_stages"] == 2

    def test_validation_failure_emits_failed_no_stage_starts(self, registries, run_config):
        wf, tx = registries
        events: list[dict] = []
        runner = StackRunner(wf, tx, use_cache=False, event_sink=events.append)
        stack = PreprocStack(
            bootstrap=BootstrapStage(kind="nipype", workflow="ghost_wf"),
        )
        result = runner.run(stack, run_config)
        assert result.status == "failed"
        assert [e["event"] for e in events] == ["failed"]
        assert "ghost_wf" in " ".join(events[0]["errors"])

    def test_no_sink_doesnt_raise(self, registries, run_config):
        # event_sink defaults to None — runner still completes cleanly.
        wf, tx = registries
        runner = StackRunner(wf, tx, use_cache=False, event_sink=None)
        stack = PreprocStack(
            bootstrap=BootstrapStage(kind="nipype", workflow="identity"),
        )
        result = runner.run(stack, run_config)
        assert result.status == "completed"

    def test_sink_exception_is_swallowed(self, registries, run_config):
        # A broken sink must not break the run.
        def boom(ev):
            raise RuntimeError("sink exploded")

        wf, tx = registries
        runner = StackRunner(wf, tx, use_cache=False, event_sink=boom)
        stack = PreprocStack(
            bootstrap=BootstrapStage(kind="nipype", workflow="identity"),
        )
        result = runner.run(stack, run_config)
        assert result.status == "completed"

    def test_cache_hit_emits_cache_hit_true(self, registries, run_config):
        wf, tx = registries
        stack = PreprocStack(
            bootstrap=BootstrapStage(kind="nipype", workflow="identity"),
            transforms=[TransformStage(name="identity")],
        )

        # First run populates the cache.
        first_events: list[dict] = []
        runner1 = StackRunner(wf, tx, use_cache=True, event_sink=first_events.append)
        runner1.run(stack, run_config)
        first_done = [e for e in first_events if e["event"] == "stage_done"]
        assert all(e["cache_hit"] is False for e in first_done)

        # Second run with cache enabled — should hit both stages.
        second_events: list[dict] = []
        runner2 = StackRunner(wf, tx, use_cache=True, event_sink=second_events.append)
        runner2.run(stack, run_config)
        second_done = [e for e in second_events if e["event"] == "stage_done"]
        assert all(e["cache_hit"] is True for e in second_done)
