"""RunManager — launches and tracks pipeline runs in background threads."""

from __future__ import annotations

import logging
import queue
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fmriflow.server.ui_capture import UICaptureProxy

logger = logging.getLogger(__name__)


@dataclass
class RunHandle:
    """A single pipeline run executing in a background thread."""
    run_id: str
    config: dict
    config_path: str | None = None   # if launched from a file
    status: str = 'pending'          # pending | running | done | failed
    error: str | None = None
    events: list[dict] = field(default_factory=list)
    event_queue: queue.Queue = field(default_factory=queue.Queue)
    _thread: threading.Thread | None = field(default=None, repr=False)

    def start(self) -> None:
        """Launch the pipeline in a daemon thread."""
        self.status = 'running'
        self._thread = threading.Thread(
            target=self._execute, daemon=True, name=f"run-{self.run_id}"
        )
        self._thread.start()

    def _execute(self) -> None:
        """Run the pipeline and capture UI events."""
        capture = UICaptureProxy(self.event_queue)
        capture.install()
        file_handler: logging.FileHandler | None = None
        try:
            from fmriflow.pipeline import Pipeline

            if self.config_path:
                pipeline = Pipeline.from_yaml(self.config_path)
                # Apply any overrides
                if self.config:
                    for key, value in self.config.items():
                        pipeline.config[key] = value
            else:
                pipeline = Pipeline(self.config)

            # Set up file logging
            output_dir = pipeline.config.get('reporting', {}).get(
                'output_dir', './results')
            file_handler = self._setup_logging(output_dir)

            ctx = pipeline.run()
            self.status = 'done'

            # Save run summary
            self._save_summary(ctx, output_dir)

            # Push completion event
            self.event_queue.put({
                'event': 'run_done',
                'total_elapsed': ctx.run_summary.total_elapsed_s
                if hasattr(ctx, 'run_summary') and ctx.run_summary else 0,
            })
        except Exception as e:
            self.status = 'failed'
            self.error = str(e)
            self.event_queue.put({
                'event': 'run_failed',
                'error': str(e),
            })
            logger.error("Run %s failed: %s", self.run_id, e, exc_info=True)
        finally:
            capture.uninstall()
            if file_handler is not None:
                logging.getLogger().removeHandler(file_handler)
                file_handler.close()

    def _setup_logging(self, output_dir: str) -> logging.FileHandler:
        """Set up file logging for this run. Returns the handler for later cleanup."""
        log_dir = Path(output_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"pipeline_{self.run_id}.log"

        file_handler = logging.FileHandler(log_path, mode='w')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
        ))

        # Ensure this handler only records log messages from this run's thread.
        # Threads are named "run-{run_id}" in start(), and logging records include
        # the originating thread name in record.threadName.
        class RunThreadFilter(logging.Filter):
            def __init__(self, thread_name: str) -> None:
                super().__init__()
                self._thread_name = thread_name

            def filter(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
                return record.threadName == self._thread_name

        thread_name = f"run-{self.run_id}"
        file_handler.addFilter(RunThreadFilter(thread_name))
        logging.getLogger().addHandler(file_handler)
        return file_handler

    def _save_summary(self, ctx: Any, output_dir: str) -> None:
        """Save run summary JSON."""
        if ctx is None or not hasattr(ctx, 'run_summary'):
            return
        summary = ctx.run_summary
        out = Path(output_dir)
        try:
            summary.save_json(out / 'run_summary.json')
        except Exception:
            logger.warning("Could not save run_summary.json", exc_info=True)
        try:
            from fmriflow.core.run_chart import save_timeline_chart
            save_timeline_chart(summary, out / 'run_timeline.png')
        except Exception:
            pass

    def drain_events(self) -> list[dict]:
        """Drain all pending events from the queue."""
        events = []
        while True:
            try:
                event = self.event_queue.get_nowait()
                events.append(event)
                self.events.append(event)
            except queue.Empty:
                break
        return events


class RunManager:
    """Manages background pipeline runs."""

    def __init__(self):
        self.active_runs: dict[str, RunHandle] = {}

    def start_run(self, config: dict) -> str:
        """Launch a pipeline run from a config dict. Returns the run ID."""
        run_id = uuid.uuid4().hex[:12]
        handle = RunHandle(run_id=run_id, config=config)
        self.active_runs[run_id] = handle
        handle.start()
        logger.info("Started run %s", run_id)
        return run_id

    def start_run_from_config(self, config_path: str, overrides: dict | None = None) -> str:
        """Launch a pipeline run from a YAML config file. Returns the run ID."""
        run_id = uuid.uuid4().hex[:12]
        handle = RunHandle(
            run_id=run_id,
            config=overrides or {},
            config_path=config_path,
        )
        self.active_runs[run_id] = handle
        handle.start()
        logger.info("Started run %s from config %s", run_id, config_path)
        return run_id

    def get_status(self, run_id: str) -> dict | None:
        """Get current status and events for a run."""
        handle = self.active_runs.get(run_id)
        if handle is None:
            return None
        new_events = handle.drain_events()
        return {
            'run_id': handle.run_id,
            'status': handle.status,
            'error': handle.error,
            'new_events': new_events,
            'all_events': handle.events,
        }

    def cleanup(self, max_age_s: float = 3600) -> None:
        """Remove completed runs older than max_age_s."""
        to_remove = []
        for run_id, handle in self.active_runs.items():
            if handle.status in ('done', 'failed'):
                to_remove.append(run_id)
        for run_id in to_remove:
            del self.active_runs[run_id]
