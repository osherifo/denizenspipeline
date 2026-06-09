"""Detached entry point for executing a PreprocStack.

The server's StackManager spawns this CLI as a detached subprocess
(``start_new_session=True``) so the run survives server restarts.
The CLI reads its configuration from a JSON file, runs the stack
synchronously via ``StackRunner``, and writes status into the
``RunStateFile`` so reattach can pick up.

Invocation::

    python -m fmriflow.preproc.stack_runner_cli \\
        --run-id <id> \\
        --config <path-to-job.json>

The job JSON has the shape::

    {
        "stack": { ... PreprocStack serialised ... },
        "run_config": { ... StackRunConfig serialised ... },
        "use_cache": true
    }

On completion, ``state.json`` (under ``runs/{run_id}/``) is
updated with ``status`` ("done" or "failed"), the produced
manifest's path, and a structured ``result`` payload containing
per-stage snapshots + cache hits + the bootstrap fingerprint.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import traceback
from dataclasses import asdict
from pathlib import Path

from fmriflow.preproc.stack import PreprocStack
from fmriflow.preproc.stack_events import EventWriter
from fmriflow.preproc.stack_runner import (
    StackRunConfig,
    StackRunner,
)
from fmriflow.preproc.transform_registry import TransformRegistry
from fmriflow.preproc.workflow_registry import WorkflowRegistry
from fmriflow.server.services.run_registry import RunRegistry

logger = logging.getLogger(__name__)


def _load_job(
    path: Path,
) -> tuple[PreprocStack, StackRunConfig, bool, int | None]:
    data = json.loads(path.read_text())
    stack = PreprocStack.from_dict(data["stack"])

    rc = data["run_config"]
    run_config = StackRunConfig(
        subject=rc["subject"],
        output_dir=Path(rc["output_dir"]),
        bids_dir=Path(rc["bids_dir"]) if rc.get("bids_dir") else None,
        derivatives_dir=(
            Path(rc["derivatives_dir"]) if rc.get("derivatives_dir") else None
        ),
        dataset=rc.get("dataset", "unknown"),
        sessions=list(rc.get("sessions") or []),
        task=rc.get("task"),
    )

    use_cache = bool(data.get("use_cache", True))
    force_from_stage = data.get("force_from_stage")
    if force_from_stage is not None:
        force_from_stage = int(force_from_stage)
    return stack, run_config, use_cache, force_from_stage


def _result_payload(result) -> dict:
    """Serialise StackRunResult into a JSON-able dict for state.json."""
    return {
        "status": result.status,
        "bootstrap_fingerprint": result.bootstrap_fingerprint,
        "stage_cache_hits": list(result.stage_cache_hits),
        "duration_s": result.duration_s,
        "errors": list(result.errors),
        "n_stages": len(result.stage_manifests),
        "stage_manifests": [m.to_dict() for m in result.stage_manifests],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fmriflow-stack-runner")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--config", required=True, type=Path,
                        help="JSON file with stack + run_config + use_cache.")
    parser.add_argument("--registry-root", default=None,
                        help="Override RunRegistry root (tests only).")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    registry = RunRegistry(
        root=Path(args.registry_root) if args.registry_root else None,
    )

    state = registry.load(args.run_id)
    if state is None:
        # Shouldn't happen — the manager registers state before spawning us.
        logger.error("RunStateFile for run_id=%r not found", args.run_id)
        return 2

    try:
        stack, run_config, use_cache, force_from_stage = _load_job(args.config)
    except Exception as e:
        logger.exception("Could not load job config %s", args.config)
        state.status = "failed"
        state.error = f"Job-config load failed: {e}"
        state.finished_at = time.time()
        registry.update(state)
        return 3

    # Discover registries fresh in this subprocess.
    wf_reg = WorkflowRegistry()
    wf_reg.discover()
    tx_reg = TransformRegistry()
    tx_reg.discover()

    # Stream live events into <run_dir>/events.jsonl for the
    # server's WebSocket endpoint to tail.
    events_path = registry.run_dir(args.run_id) / "events.jsonl"
    event_writer = EventWriter(events_path)

    runner = StackRunner(
        wf_reg, tx_reg,
        use_cache=use_cache,
        event_sink=event_writer,
        force_from_stage=force_from_stage,
    )

    try:
        try:
            result = runner.run(stack, run_config)
        except Exception as e:
            logger.exception("StackRunner raised unexpectedly")
            state.status = "failed"
            state.error = f"{type(e).__name__}: {e}"
            state.finished_at = time.time()
            state.result = {
                "status": "failed",
                "errors": [traceback.format_exc()],
            }
            registry.update(state)
            return 4

        # Persist the final manifest alongside the run dir.
        manifest_path = None
        if result.manifest is not None:
            run_dir = registry.run_dir(args.run_id)
            manifest_path = run_dir / "stack_manifest.json"
            result.manifest.save(manifest_path)

        state.status = "done" if result.status == "completed" else "failed"
        state.error = "; ".join(result.errors) if result.errors else None
        state.finished_at = time.time()
        state.manifest_path = str(manifest_path) if manifest_path else None
        state.result = _result_payload(result)
        registry.update(state)

        return 0 if result.status == "completed" else 1
    finally:
        # Close the events.jsonl writer on every exit path —
        # exception, success, or early return — so we don't leak the
        # file descriptor + delay the final flush.
        event_writer.close()


if __name__ == "__main__":
    sys.exit(main())
