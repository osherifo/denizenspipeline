"""Phase 5 — direct invocation of the stack-runner CLI shim.

The CLI is what the StackManager spawns as a detached subprocess.
We invoke it directly (no FastAPI) to confirm the end-to-end:

- Load job.json → discover registries → run StackRunner → write
  manifest + state.json.
- ``state.status`` reflects completion (``done`` / ``failed``).
- ``state.result`` carries the per-stage manifests, cache hits,
  and bootstrap fingerprint.
- The final manifest lands on disk at ``state.manifest_path``.

These tests run the actual subprocess. The ``identity`` workflow
+ ``identity`` transform finish in milliseconds; no FSL / ANTs /
nipype involved.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from fmriflow.preproc.stack import (
    BootstrapStage,
    PreprocStack,
    TransformStage,
)
from fmriflow.server.services.run_registry import RunRegistry, RunStateFile


def _write_job(
    path: Path,
    stack: PreprocStack,
    output_dir: Path,
    *,
    subject: str = "sub01",
) -> None:
    path.write_text(
        json.dumps(
            {
                "stack": stack.to_dict(),
                "run_config": {
                    "subject": subject,
                    "output_dir": str(output_dir),
                    "dataset": "study1",
                    "sessions": ["ses01"],
                    "task": "story",
                },
                "use_cache": True,
            },
            indent=2,
        )
    )


def _run_cli(registry_root: Path, run_id: str, job_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable, "-m", "fmriflow.preproc.stack_runner_cli",
            "--run-id", run_id,
            "--config", str(job_path),
            "--registry-root", str(registry_root),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )


class TestCliHappyPath:
    def test_identity_stack_succeeds(self, tmp_path):
        registry = RunRegistry(root=tmp_path / "runs")
        output_dir = tmp_path / "out"

        run_id = "stack_test_001"
        state = RunStateFile(
            run_id=run_id,
            kind="stack",
            backend="nipype",
            subject="sub01",
            status="running",
            started_at=0.0,
        )
        registry.register(state)

        job_path = tmp_path / "job.json"
        stack = PreprocStack(
            bootstrap=BootstrapStage(kind="nipype", workflow="identity"),
            transforms=[TransformStage(name="identity")],
        )
        _write_job(job_path, stack, output_dir)

        result = _run_cli(tmp_path / "runs", run_id, job_path)
        assert result.returncode == 0, (
            f"CLI failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

        reloaded = registry.load(run_id)
        assert reloaded is not None
        assert reloaded.status == "done"
        assert reloaded.error is None

        # state.result carries the structured payload.
        assert reloaded.result is not None
        assert reloaded.result["status"] == "completed"
        assert reloaded.result["n_stages"] == 2
        assert len(reloaded.result["stage_manifests"]) == 2
        assert reloaded.result["bootstrap_fingerprint"]
        # First run, both stages — both cache misses.
        assert reloaded.result["stage_cache_hits"] == [False, False]

        # Manifest written to disk.
        assert reloaded.manifest_path is not None
        manifest_path = Path(reloaded.manifest_path)
        assert manifest_path.is_file()


class TestCliFailureModes:
    def test_bad_job_json_fails_cleanly(self, tmp_path):
        registry = RunRegistry(root=tmp_path / "runs")

        run_id = "stack_test_bad"
        registry.register(RunStateFile(
            run_id=run_id, kind="stack", backend="nipype",
            subject="sub01", status="running",
        ))

        job_path = tmp_path / "bad.json"
        job_path.write_text("not valid json {")

        result = _run_cli(tmp_path / "runs", run_id, job_path)
        assert result.returncode != 0

        reloaded = registry.load(run_id)
        assert reloaded is not None
        assert reloaded.status == "failed"
        assert "load failed" in (reloaded.error or "").lower()

    def test_unknown_workflow_fails_cleanly(self, tmp_path):
        registry = RunRegistry(root=tmp_path / "runs")

        run_id = "stack_test_unknown"
        registry.register(RunStateFile(
            run_id=run_id, kind="stack", backend="nipype",
            subject="sub01", status="running",
        ))

        job_path = tmp_path / "job.json"
        stack = PreprocStack(
            bootstrap=BootstrapStage(kind="nipype", workflow="ghost_workflow"),
        )
        _write_job(job_path, stack, tmp_path / "out")

        result = _run_cli(tmp_path / "runs", run_id, job_path)
        # Returns 1 (completed=False, errors present), not 0.
        assert result.returncode == 1

        reloaded = registry.load(run_id)
        assert reloaded is not None
        assert reloaded.status == "failed"
        assert reloaded.result is not None
        assert any("ghost_workflow" in e for e in reloaded.result["errors"])
