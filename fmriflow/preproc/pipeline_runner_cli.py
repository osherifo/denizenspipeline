"""Detached entry point for one pipeline run.

The server's :class:`~fmriflow.server.services.preproc_run_manager.PreprocRunManager`
spawns this as its own session so the run survives a server restart.
It reads ``job.json`` (pipeline + run request), discovers the node
library, runs the pipeline with events streamed to ``events.jsonl``, and
writes the terminal status + result into the run's ``state.json``.

Invocation::

    python -m fmriflow.preproc.pipeline_runner_cli --run-id <id> --config <job.json>

``job.json``::

    {"pipeline": {...Pipeline.to_dict()...}, "request": {...PipelineRunRequest.to_dict()...}}

SIGTERM (a cancel) is forwarded to every live child process group
(docker / apptainer apps) before exiting.
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import time
import traceback
from pathlib import Path

from fmriflow.preproc.graph import Pipeline, PipelineRunRequest
from fmriflow.preproc.node_registry import NodeRegistry
from fmriflow.preproc.pipeline_runner import PipelineRunner
from fmriflow.preproc.stack_events import EventWriter
from fmriflow.server.services.run_registry import RunRegistry

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = "preproc_manifest.json"


def _load_job(path: Path) -> tuple[Pipeline, PipelineRunRequest]:
    data = json.loads(path.read_text())
    return Pipeline.from_dict(data["pipeline"]), PipelineRunRequest.from_dict(data["request"])


def _install_sigterm(registry: RunRegistry, run_id: str) -> None:
    from fmriflow.preproc.container import terminate_children

    def _handler(signum, frame):  # pragma: no cover — signal path
        logger.warning("SIGTERM: terminating child process groups and exiting")
        terminate_children()
        state = registry.load(run_id)
        if state is not None and state.status == "running":
            state.status = "cancelled"
            state.finished_at = time.time()
            registry.update(state)
        sys.exit(143)

    signal.signal(signal.SIGTERM, _handler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fmriflow-pipeline-runner")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--registry-root", default=None)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    registry = RunRegistry(root=Path(args.registry_root) if args.registry_root else None)
    state = registry.load(args.run_id)
    if state is None:
        logger.error("RunStateFile for run_id=%r not found", args.run_id)
        return 2
    _install_sigterm(registry, args.run_id)

    try:
        pipeline, request = _load_job(args.config)
    except Exception as e:
        logger.exception("Could not load job %s", args.config)
        state.status = "failed"
        state.error = f"job load failed: {e}"
        state.finished_at = time.time()
        registry.update(state)
        return 3

    node_registry = NodeRegistry().discover()
    run_dir = registry.run_dir(args.run_id)
    events_path = run_dir / "events.jsonl"
    writer = EventWriter(events_path)
    runner = PipelineRunner(
        node_registry, run_id=args.run_id, event_sink=writer,
        events_path=events_path, crash_dir=run_dir / "crash",
    )
    try:
        try:
            result = runner.run(pipeline, request)
        except Exception as e:
            logger.exception("PipelineRunner raised")
            current = registry.load(args.run_id) or state
            if current.status != "cancelled":
                current.status = "failed"
                current.error = f"{type(e).__name__}: {e}"
                current.finished_at = time.time()
                current.result = {"status": "failed", "errors": [traceback.format_exc()]}
                registry.update(current)
            return 4

        manifest_path = None
        if result.manifest is not None:
            manifest_path = run_dir / MANIFEST_FILENAME
            result.manifest.save(manifest_path)
            # Also drop a copy next to the outputs, where downstream stages look.
            try:
                out_copy = Path(request.output_dir) / MANIFEST_FILENAME
                out_copy.parent.mkdir(parents=True, exist_ok=True)
                out_copy.write_text(manifest_path.read_text())
            except OSError:
                logger.warning("could not copy manifest into %s", request.output_dir, exc_info=True)

        current = registry.load(args.run_id) or state
        if current.status == "cancelled":
            return 1
        current.status = "done" if result.status == "completed" else "failed"
        current.error = "; ".join(e.splitlines()[0] for e in result.errors) if result.errors else None
        current.finished_at = time.time()
        current.manifest_path = str(manifest_path) if manifest_path else None
        current.result = result.to_dict()
        current.params = {**(current.params or {}), "work_dir": result.work_dir}
        registry.update(current)
        return 0 if result.status == "completed" else 1
    finally:
        writer.close()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
