"""Autoflatten manager — background execution with log streaming."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class AutoflattenRunHandle:
    """Tracks a running autoflatten job."""
    run_id: str
    subject: str
    status: str = "running"  # running, done, failed
    events: list[dict] = field(default_factory=list)
    _pending: list[dict] = field(default_factory=list)
    result: dict | None = None
    error: str | None = None
    started_at: float = 0.0
    finished_at: float = 0.0

    def push_event(self, event: dict) -> None:
        event.setdefault("timestamp", time.time())
        self.events.append(event)
        self._pending.append(event)

    def drain_events(self) -> list[dict]:
        out = list(self._pending)
        self._pending.clear()
        return out


class AutoflattenManager:
    """Manages autoflatten runs with background execution and log streaming."""

    def __init__(self) -> None:
        self.active_runs: dict[str, AutoflattenRunHandle] = {}

    def start_run(self, params: dict) -> str:
        """Start an autoflatten run in a background thread."""
        run_id = f"autoflatten_{params.get('subject', 'unknown')}_{uuid.uuid4().hex[:8]}"
        handle = AutoflattenRunHandle(
            run_id=run_id,
            subject=params.get("subject", "unknown"),
            started_at=time.time(),
        )
        self.active_runs[run_id] = handle

        thread = threading.Thread(
            target=self._execute_run,
            args=(handle, params),
            daemon=True,
        )
        thread.start()
        return run_id

    def _execute_run(self, handle: AutoflattenRunHandle, params: dict) -> None:
        """Execute autoflatten in a background thread, capturing log output."""
        # Capture log records from the autoflatten module (and its sub-loggers)
        capture = _LogCapture(handle)
        af_logger = logging.getLogger("fmriflow.preproc.autoflatten")
        af_logger.addHandler(capture)
        # Also capture the root fmriflow logger for broader coverage
        fm_logger = logging.getLogger("fmriflow")
        fm_logger.addHandler(capture)

        try:
            from fmriflow.preproc.autoflatten import (
                AutoflattenConfig,
                AutoflattenRecord,
                run_autoflatten,
            )

            config = AutoflattenConfig(
                subjects_dir=params["subjects_dir"],
                subject=params["subject"],
                hemispheres=params.get("hemispheres", "both"),
                backend=params.get("backend", "pyflatten"),
                parallel=params.get("parallel", True),
                overwrite=params.get("overwrite", False),
                template_file=params.get("template_file"),
                output_dir=params.get("output_dir"),
                import_to_pycortex=params.get("import_to_pycortex", True),
                pycortex_surface_name=params.get("pycortex_surface_name"),
                flat_patch_lh=params.get("flat_patch_lh"),
                flat_patch_rh=params.get("flat_patch_rh"),
            )

            errors = config.validate()
            if errors:
                raise ValueError("; ".join(errors))

            handle.push_event({
                "event": "started",
                "message": f"Starting autoflatten for {config.subject}",
            })

            result = run_autoflatten(config)
            record = AutoflattenRecord.from_result(result, config)

            handle.result = {
                "result": {
                    "subject": result.subject,
                    "source": result.source,
                    "hemispheres": result.hemispheres,
                    "flat_patches": result.flat_patches,
                    "visualizations": result.visualizations,
                    "pycortex_surface": result.pycortex_surface,
                    "elapsed_s": result.elapsed_s,
                },
                "record": record.to_dict(),
            }
            handle.status = "done"
            handle.finished_at = time.time()
            handle.push_event({
                "event": "done",
                "message": f"Autoflatten complete ({result.source})",
                "source": result.source,
                "pycortex_surface": result.pycortex_surface,
                "elapsed": handle.finished_at - handle.started_at,
            })

        except Exception as e:
            handle.status = "failed"
            handle.error = str(e)
            handle.finished_at = time.time()
            handle.push_event({
                "event": "failed",
                "error": str(e),
                "elapsed": handle.finished_at - handle.started_at,
            })
            logger.error("Autoflatten failed: %s", e, exc_info=True)

        finally:
            af_logger.removeHandler(capture)
            fm_logger.removeHandler(capture)


class _LogCapture(logging.Handler):
    """Logging handler that pushes log records as events to a run handle."""

    def __init__(self, run_handle: AutoflattenRunHandle):
        super().__init__()
        self.run_handle = run_handle
        self.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        # Avoid infinite recursion if this handler itself logs
        if record.name == __name__:
            return
        try:
            self.run_handle.push_event({
                "event": "log",
                "level": record.levelname,
                "message": self.format(record),
            })
        except Exception:
            pass
