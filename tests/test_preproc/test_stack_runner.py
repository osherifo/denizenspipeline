"""Phase 4a — end-to-end stack-runner tests.

Exercises the runner with the built-in identity primitives:

- ``passthrough`` + identity transform — happy path with no nipype
  workflow involvement.
- ``nipype:identity`` + identity transform — happy path through
  the workflow registry.
- 3-transform stack accumulates ``StepRecord`` entries in order
  with monotone ``input_stage`` indices.
- Unknown bootstrap kind, missing workflow name, unknown transform,
  preflight failure all return failed ``StackRunResult`` with
  descriptive errors and no partial side-effects on subsequent
  stages.
- Per-stage manifest snapshots returned and indexed correctly;
  ``output_dir`` pointer moves to each stage's out-dir.

Future phases extend with fingerprint caching (Phase 4b) and
resume (Phase 4c).
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from fmriflow.preproc.stack import (
    BootstrapStage,
    PreprocStack,
    TransformStage,
)
from fmriflow.preproc.stack_runner import (
    StackRunConfig,
    StackRunner,
    StackRunResult,
)
from fmriflow.preproc.transform_registry import TransformRegistry
from fmriflow.preproc.workflow_registry import WorkflowRegistry


# ── Shared fixtures ────────────────────────────────────────────────


@pytest.fixture
def registries(tmp_path):
    """Discovered registries scoped to a fresh user dir."""
    wf_reg = WorkflowRegistry(user_dir=tmp_path / "_wf_user")
    wf_reg.discover()
    tx_reg = TransformRegistry(user_dir=tmp_path / "_tx_user")
    tx_reg.discover()
    return wf_reg, tx_reg


@pytest.fixture
def runner(registries):
    wf_reg, tx_reg = registries
    return StackRunner(wf_reg, tx_reg)


@pytest.fixture
def run_config(tmp_path):
    return StackRunConfig(
        subject="sub01",
        output_dir=tmp_path / "out",
        bids_dir=tmp_path / "bids",
        dataset="study1",
        sessions=["ses01"],
        task="story",
    )


# ── Happy paths ────────────────────────────────────────────────────


class TestPassthroughBootstrap:
    def test_no_transforms(self, runner, run_config):
        stack = PreprocStack(bootstrap=BootstrapStage(kind="passthrough"))
        result = runner.run(stack, run_config)

        assert result.status == "completed"
        assert result.errors == []
        assert len(result.stage_manifests) == 1
        assert result.manifest is result.stage_manifests[0]
        assert result.manifest.backend == "passthrough"
        assert result.manifest.subject == "sub01"
        assert result.manifest.runs == []
        assert result.manifest.additional_steps == []
        assert result.duration_s >= 0

    def test_one_identity_transform(self, runner, run_config):
        stack = PreprocStack(
            bootstrap=BootstrapStage(kind="passthrough"),
            transforms=[TransformStage(name="identity")],
        )
        result = runner.run(stack, run_config)

        assert result.status == "completed"
        assert len(result.stage_manifests) == 2
        assert len(result.manifest.additional_steps) == 1

        step = result.manifest.additional_steps[0]
        assert step.name == "identity"
        assert step.version == "0.1.0"
        assert step.input_stage == 0
        # out_dir should have been created.
        assert Path(step.output_dir).is_dir()


class TestNipypeIdentityBootstrap:
    def test_no_transforms(self, runner, run_config):
        stack = PreprocStack(
            bootstrap=BootstrapStage(kind="nipype", workflow="identity"),
        )
        result = runner.run(stack, run_config)

        assert result.status == "completed"
        assert len(result.stage_manifests) == 1
        assert result.manifest.backend == "nipype"
        assert result.manifest.parameters == {"workflow": "identity"}

    def test_one_identity_transform(self, runner, run_config):
        stack = PreprocStack(
            bootstrap=BootstrapStage(kind="nipype", workflow="identity"),
            transforms=[TransformStage(name="identity")],
        )
        result = runner.run(stack, run_config)

        assert result.status == "completed"
        assert len(result.manifest.additional_steps) == 1


class TestMultipleTransforms:
    def test_three_transforms_in_order(self, runner, run_config):
        stack = PreprocStack(
            bootstrap=BootstrapStage(kind="passthrough"),
            transforms=[
                TransformStage(name="identity", params={"tag": "a"}),
                TransformStage(name="identity", params={"tag": "b"}),
                TransformStage(name="identity", params={"tag": "c"}),
            ],
        )
        result = runner.run(stack, run_config)

        assert result.status == "completed"
        assert len(result.stage_manifests) == 4  # bootstrap + 3 transforms
        assert len(result.manifest.additional_steps) == 3

        # StepRecords are in order, with monotone input_stage.
        for i, step in enumerate(result.manifest.additional_steps):
            assert step.name == "identity"
            assert step.input_stage == i
            assert step.params == {"tag": "abc"[i]}

        # output_dir on final manifest points at the last stage's dir.
        last_step = result.manifest.additional_steps[-1]
        assert result.manifest.output_dir == last_step.output_dir
        # The per-stage snapshot's output_dir matches its own step.
        for i in range(1, 4):
            snap = result.stage_manifests[i]
            assert snap.output_dir == snap.additional_steps[-1].output_dir


# ── Failure modes ──────────────────────────────────────────────────


class TestUnknownBootstrapKind:
    def test_fails_cleanly_with_errors(self, runner, run_config):
        # Cannot instantiate PreprocStack with an unknown kind via the
        # public constructor *if* we validate at constructor-time; but
        # the dataclass is frozen and unchecked, so we can simulate
        # a hand-rolled bad stack.
        stack = PreprocStack(bootstrap=BootstrapStage(kind="unicorn"))
        result = runner.run(stack, run_config)

        assert result.status == "failed"
        assert result.manifest is None
        assert any("unicorn" in e for e in result.errors)
        assert any("Known kinds" in e for e in result.errors)


class TestNipypeMissingWorkflow:
    def test_missing_workflow_name_blocks(self, runner, run_config):
        stack = PreprocStack(
            bootstrap=BootstrapStage(kind="nipype", workflow=None),
        )
        result = runner.run(stack, run_config)
        assert result.status == "failed"
        assert any("requires a workflow name" in e for e in result.errors)

    def test_unknown_workflow_name_blocks(self, runner, run_config):
        stack = PreprocStack(
            bootstrap=BootstrapStage(kind="nipype", workflow="not_a_real_wf"),
        )
        result = runner.run(stack, run_config)
        assert result.status == "failed"
        assert any("not_a_real_wf" in e for e in result.errors)


class TestUnknownTransform:
    def test_fails_before_bootstrap_runs(self, runner, run_config):
        stack = PreprocStack(
            bootstrap=BootstrapStage(kind="passthrough"),
            transforms=[TransformStage(name="not_a_real_transform")],
        )
        result = runner.run(stack, run_config)

        assert result.status == "failed"
        # Caught in validation — no partial stages.
        assert result.stage_manifests == []
        assert any("not_a_real_transform" in e for e in result.errors)


class TestPreflightFailureBlocks:
    def test_workflow_with_missing_tool_blocks(self, runner, run_config, registries, caplog):
        """If a workflow declares a missing tool, the runner refuses
        to start — preflight runs in _validate."""
        wf_reg, tx_reg = registries

        # Register a workflow with an impossible REQUIRED_TOOL.
        from fmriflow.preproc.workflow_registry import (
            register_preproc_workflow,
            _REGISTRY as _WF_REGISTRY,
        )

        @register_preproc_workflow("needs_fake_tool")
        class _NeedsFakeTool:
            name = "needs_fake_tool"
            version = "0.1"
            description = "test workflow with missing tool"
            PARAM_SCHEMA: dict = {}
            REQUIRED_PYTHON: list[str] = []
            REQUIRED_TOOLS = ["totally_fake_executable_xyz"]
            REQUIRED_ENV: list[str] = []
            CONTAINER = None

            def validate(self, config):
                return []

            def build(self, config):
                return None

            def to_manifest(self, config, wf_outputs):
                return None

        # Re-discover so our new registration is claimed by some tier.
        wf_reg.discover()

        try:
            stack = PreprocStack(
                bootstrap=BootstrapStage(kind="nipype", workflow="needs_fake_tool"),
            )
            with caplog.at_level(logging.WARNING):
                result = runner.run(stack, run_config)

            assert result.status == "failed"
            assert any("totally_fake_executable_xyz" in e for e in result.errors)
            # No stages ran — bootstrap was blocked by preflight.
            assert result.stage_manifests == []
        finally:
            # Clean up so subsequent tests don't trip over our test
            # registration.
            _WF_REGISTRY.pop("needs_fake_tool", None)
