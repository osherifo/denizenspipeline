"""WorkflowManager — orchestrates end-to-end workflow runs.

A workflow is a sequence of stage references (convert / preproc /
autoflatten / analysis). The orchestrator loops over them and for
each one:

  1. Calls the stage's existing ``start_run_from_config_file`` method.
  2. Waits for the child run's handle to transition out of ``running``
     (polling the stage manager's ``active_runs`` dict every 2 s).
  3. If the child ended ``done`` → advance to next stage.
     Otherwise → stop and mark the workflow ``failed``.

Each child run still uses its own per-stage detach/reattach machinery,
so individual stage subprocesses survive server restarts. The
workflow-level orchestration itself is in-process (no workflow
reattach across server restarts in v1) — if the server dies mid-
workflow, the current stage's subprocess keeps running but the
workflow's "kick off next stage when current finishes" intent is lost.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from fmriflow.server.services.run_registry import RunRegistry, RunStateFile
from fmriflow.server.services.workflow_config_store import (
    WorkflowStageRef,
    parse_stage_refs,
)

logger = logging.getLogger(__name__)


STAGE_KEYS: tuple[str, ...] = ("convert", "preproc", "autoflatten", "analysis")


@dataclass
class WorkflowStageStatus:
    stage: str
    config: str
    status: str = "pending"       # pending | running | done | failed | cancelled
    run_id: str | None = None     # child run_id assigned by the stage manager
    started_at: float = 0.0
    finished_at: float = 0.0
    error: str | None = None


@dataclass
class WorkflowRunHandle:
    """A single end-to-end workflow execution."""
    run_id: str
    name: str
    status: str = "running"       # running | done | failed | cancelled
    started_at: float = 0.0
    finished_at: float = 0.0
    error: str | None = None
    stages: list[WorkflowStageStatus] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    _pending: list[dict] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _cancel: threading.Event = field(default_factory=threading.Event)
    config_path: str | None = None

    def push_event(self, event: dict) -> None:
        event.setdefault("timestamp", time.time())
        with self._lock:
            self.events.append(event)
            self._pending.append(event)

    def drain_events(self) -> list[dict]:
        with self._lock:
            out = list(self._pending)
            self._pending.clear()
        return out

    def to_summary(self) -> dict:
        return {
            "run_id": self.run_id,
            "name": self.name,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "config_path": self.config_path,
            "stages": [
                {
                    "stage": s.stage,
                    "config": s.config,
                    "status": s.status,
                    "run_id": s.run_id,
                    "started_at": s.started_at,
                    "finished_at": s.finished_at,
                    "error": s.error,
                }
                for s in self.stages
            ],
        }


class WorkflowManager:
    """Orchestrates workflow runs by calling into the per-stage managers."""

    def __init__(
        self,
        # Injected at wiring time in app.py
        stage_managers: dict[str, Any] | None = None,
        registry: RunRegistry | None = None,
    ):
        self.stage_managers: dict[str, Any] = stage_managers or {}
        self.active_runs: dict[str, WorkflowRunHandle] = {}
        self.registry = registry or RunRegistry()

    def bind_stage_managers(self, **managers) -> None:
        """Late-bind stage managers (app.py builds them, wires via this)."""
        self.stage_managers.update(managers)

    # ── Launch ───────────────────────────────────────────────────────

    def start_workflow_from_file(self, workflow_path: str) -> str:
        """Parse a workflow YAML, register state, kick off the orchestrator."""
        import yaml as _yaml

        path = Path(workflow_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Workflow config not found: {path}")
        with open(path) as f:
            data = _yaml.safe_load(f) or {}
        section = data.get("workflow")
        if not isinstance(section, dict):
            raise ValueError(
                f"Config '{path.name}' has no 'workflow:' section"
            )
        refs = parse_stage_refs(section)

        # Resolve each stage's config path relative to the workflow YAML's
        # parent dir when the ref is relative.
        resolved_refs: list[WorkflowStageRef] = []
        for r in refs:
            p = Path(r.config)
            if not p.is_absolute():
                p = (path.parent / p).resolve()
                # If that doesn't exist, try CWD-relative too.
                if not p.is_file():
                    p = Path(r.config).resolve()
            if not p.is_file():
                raise FileNotFoundError(
                    f"Stage '{r.stage}' config not found: {r.config}"
                )
            resolved_refs.append(WorkflowStageRef(stage=r.stage, config=str(p)))

        # Validate required stage managers are bound
        missing = [r.stage for r in resolved_refs if r.stage not in self.stage_managers]
        if missing:
            raise RuntimeError(
                f"Stage managers not bound for: {', '.join(missing)}"
            )

        run_id = f"workflow_{uuid.uuid4().hex[:12]}"
        now = time.time()
        name = section.get("name", path.stem)

        handle = WorkflowRunHandle(
            run_id=run_id,
            name=name,
            started_at=now,
            config_path=str(path),
            stages=[
                WorkflowStageStatus(stage=r.stage, config=r.config)
                for r in resolved_refs
            ],
        )

        state = RunStateFile(
            run_id=run_id,
            kind="workflow",
            backend="workflow",
            subject=str(section.get("subject", "")),
            status="running",
            started_at=now,
            config_path=str(path),
            params={
                "name": name,
                "stages": [{"stage": r.stage, "config": r.config} for r in resolved_refs],
            },
        )
        self.registry.register(state)
        self.active_runs[run_id] = handle

        thread = threading.Thread(
            target=self._orchestrate,
            args=(handle,),
            daemon=True,
            name=f"workflow-{run_id}",
        )
        thread.start()
        return run_id

    # ── Orchestration ────────────────────────────────────────────────

    def _orchestrate(self, handle: WorkflowRunHandle) -> None:
        handle.push_event({
            "event": "workflow_started",
            "name": handle.name,
            "n_stages": len(handle.stages),
        })

        for i, stage in enumerate(handle.stages):
            if handle._cancel.is_set():
                stage.status = "cancelled"
                handle.push_event({"event": "stage_cancelled", "stage": stage.stage})
                self._finalize(handle, "cancelled", error="cancelled before start")
                return

            stage.started_at = time.time()
            stage.status = "running"
            handle.push_event({
                "event": "stage_started",
                "stage": stage.stage,
                "index": i,
                "config": stage.config,
            })
            self._persist_state(handle)

            try:
                child_run_id = self._launch_stage(stage)
            except Exception as e:
                stage.status = "failed"
                stage.error = str(e)
                stage.finished_at = time.time()
                handle.push_event({
                    "event": "stage_failed",
                    "stage": stage.stage,
                    "error": str(e),
                })
                self._finalize(handle, "failed", error=f"{stage.stage}: {e}")
                return

            stage.run_id = child_run_id
            handle.push_event({
                "event": "stage_run_id",
                "stage": stage.stage,
                "run_id": child_run_id,
            })
            self._persist_state(handle)

            outcome = self._wait_for_stage(handle, stage, child_run_id)
            stage.finished_at = time.time()
            stage.status = outcome["status"]
            stage.error = outcome.get("error")

            handle.push_event({
                "event": "stage_finished",
                "stage": stage.stage,
                "status": stage.status,
                "elapsed": stage.finished_at - stage.started_at,
                "error": stage.error,
            })
            self._persist_state(handle)

            if stage.status != "done":
                self._finalize(
                    handle, "failed",
                    error=f"{stage.stage} {stage.status}: {stage.error or 'see stage log'}",
                )
                return

        self._finalize(handle, "done")

    def _launch_stage(self, stage: WorkflowStageStatus) -> str:
        """Dispatch the stage's start_run_from_config_file and return a run_id."""
        mgr = self.stage_managers.get(stage.stage)
        if mgr is None:
            raise RuntimeError(f"No manager registered for stage '{stage.stage}'")

        if stage.stage == "convert":
            # start_run_from_config_file returns {kind, run_id|batch_id}.
            r = mgr.start_run_from_config_file(stage.config)
            run_id = r.get("run_id") or r.get("batch_id")
            if not run_id:
                raise RuntimeError(f"convert returned no run_id: {r}")
            return run_id
        elif stage.stage == "preproc":
            return mgr.start_run_from_config_file(stage.config)
        elif stage.stage == "autoflatten":
            return mgr.start_run_from_config_file(stage.config)
        elif stage.stage == "analysis":
            return mgr.start_run_from_config(stage.config)
        else:
            raise RuntimeError(f"Unknown stage '{stage.stage}'")

    def _wait_for_stage(
        self,
        handle: WorkflowRunHandle,
        stage: WorkflowStageStatus,
        child_run_id: str,
    ) -> dict:
        """Poll the stage manager's active_runs until the child finishes.

        For convert, the id may be a batch_id — batch handles live in
        ``mgr.active_batches`` rather than ``active_runs``.
        """
        mgr = self.stage_managers.get(stage.stage)
        poll_interval = 2.0

        while True:
            if handle._cancel.is_set():
                # Best-effort cancel of the child
                cancel = getattr(mgr, "cancel_run", None)
                if callable(cancel):
                    try:
                        cancel(child_run_id)
                    except Exception:
                        pass
                return {"status": "cancelled", "error": "workflow cancelled"}

            status = self._read_child_status(mgr, stage.stage, child_run_id)
            if status is None:
                # Child vanished; likely completed and cleaned up already.
                return {"status": "done"}
            if status.get("status") in ("done", "failed", "cancelled", "lost"):
                return status
            time.sleep(poll_interval)

    def _read_child_status(
        self, mgr: Any, stage: str, child_run_id: str,
    ) -> dict | None:
        """Return {status, error} from the child manager's active set, or None."""
        if stage == "convert":
            # Batch?
            batch_handle = getattr(mgr, "active_batches", {}).get(child_run_id)
            if batch_handle is not None:
                if batch_handle.status in ("done", "failed", "cancelled"):
                    # Infer failure if any job failed
                    counts = batch_handle.summary.get("counts", {})
                    if counts.get("failed", 0) > 0:
                        return {"status": "failed", "error": f"{counts['failed']} job(s) failed"}
                    return {"status": batch_handle.status}
                return {"status": "running"}
            # Single run
            h = getattr(mgr, "active_runs", {}).get(child_run_id)
            if h is None:
                return None
            return {"status": h.status, "error": h.error}
        else:
            h = getattr(mgr, "active_runs", {}).get(child_run_id)
            if h is None:
                return None
            return {"status": h.status, "error": getattr(h, "error", None)}

    def _finalize(
        self,
        handle: WorkflowRunHandle,
        status: str,
        error: str | None = None,
    ) -> None:
        handle.status = status
        handle.error = error
        handle.finished_at = time.time()
        handle.push_event({
            "event": "workflow_finished",
            "status": status,
            "elapsed": handle.finished_at - handle.started_at,
            "error": error,
        })
        self._persist_state(handle)
        self.active_runs.pop(handle.run_id, None)

    # ── Registry + management ───────────────────────────────────────

    def _persist_state(self, handle: WorkflowRunHandle) -> None:
        state = RunStateFile(
            run_id=handle.run_id,
            kind="workflow",
            backend="workflow",
            subject="",
            status=handle.status,
            started_at=handle.started_at,
            finished_at=handle.finished_at,
            config_path=handle.config_path,
            params={
                "name": handle.name,
                "stages": [
                    {
                        "stage": s.stage,
                        "config": s.config,
                        "status": s.status,
                        "run_id": s.run_id,
                        "started_at": s.started_at,
                        "finished_at": s.finished_at,
                        "error": s.error,
                    }
                    for s in handle.stages
                ],
            },
            error=handle.error,
        )
        self.registry.update(state)

    def list_runs(self, include_finished: bool = True) -> list[dict]:
        out: dict[str, dict] = {}
        for h in self.active_runs.values():
            out[h.run_id] = h.to_summary()
        if include_finished:
            for state in self.registry.list_all():
                if state.kind != "workflow" or state.run_id in out:
                    continue
                params = state.params or {}
                out[state.run_id] = {
                    "run_id": state.run_id,
                    "name": params.get("name", ""),
                    "status": state.status,
                    "started_at": state.started_at,
                    "finished_at": state.finished_at,
                    "error": state.error,
                    "config_path": state.config_path,
                    "stages": params.get("stages", []),
                }
        return sorted(out.values(), key=lambda r: r.get("started_at") or 0, reverse=True)

    def get_run(self, run_id: str) -> dict | None:
        handle = self.active_runs.get(run_id)
        if handle is not None:
            return handle.to_summary()
        state = self.registry.load(run_id)
        if state is None or state.kind != "workflow":
            return None
        params = state.params or {}
        return {
            "run_id": state.run_id,
            "name": params.get("name", ""),
            "status": state.status,
            "started_at": state.started_at,
            "finished_at": state.finished_at,
            "error": state.error,
            "config_path": state.config_path,
            "stages": params.get("stages", []),
        }

    def cancel_run(self, run_id: str) -> dict:
        handle = self.active_runs.get(run_id)
        if handle is None:
            return {"cancelled": False, "reason": "workflow not active"}
        if handle.status != "running":
            return {"cancelled": False, "reason": f"status is {handle.status}"}
        handle._cancel.set()
        handle.push_event({"event": "workflow_cancelling"})
        # The orchestrator loop will pick up the cancel flag on its next
        # poll and forward SIGTERM to the current stage's child. We
        # don't kill anything from here — the stage manager owns the PID.
        return {"cancelled": True}
