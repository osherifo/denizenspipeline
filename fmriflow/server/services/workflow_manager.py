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
        # Workflow resumption is deferred until stage managers are
        # bound (bind_stage_managers). app.py wiring order currently
        # constructs WorkflowManager before all four stage managers
        # exist, so if we scanned the registry here we'd fail with
        # "no manager for stage 'convert'" and abandon every
        # in-flight workflow. bind_stage_managers triggers the rescan.

    def bind_stage_managers(self, **managers) -> None:
        """Late-bind stage managers (app.py builds them, wires via this).

        Also reattaches any in-flight workflows from the registry — the
        orchestrator thread is a normal Thread and doesn't survive a
        server restart, so on startup we need to re-spawn it for any
        workflow whose state.json still says ``running``.
        """
        self.stage_managers.update(managers)
        try:
            self._reattach_active_runs()
        except Exception:
            logger.warning(
                "Failed to scan workflow registry on startup",
                exc_info=True,
            )

    # ── Reattach ─────────────────────────────────────────────────────

    def _reattach_active_runs(self) -> None:
        """Rebuild handles and re-spawn orchestrator threads for
        workflows the registry still considers running."""
        for state in self.registry.list_active():
            if state.kind != "workflow":
                continue
            if state.run_id in self.active_runs:
                continue
            handle = self._rebuild_handle_from_state(state)
            if handle is None:
                continue
            self.active_runs[handle.run_id] = handle
            handle.push_event({
                "event": "workflow_reattached",
                "name": handle.name,
            })
            t = threading.Thread(
                target=self._orchestrate,
                args=(handle,),
                kwargs={"resume": True},
                daemon=True,
                name=f"workflow-{handle.run_id}",
            )
            t.start()
            logger.info(
                "Reattached workflow %s (resuming from %s)",
                handle.run_id,
                self._first_unfinished_stage(handle) or "end",
            )

    def _rebuild_handle_from_state(self, state: RunStateFile) -> WorkflowRunHandle | None:
        """Rehydrate a WorkflowRunHandle from a persisted RunStateFile."""
        params = state.params or {}
        stages_data = params.get("stages") or []
        if not stages_data:
            return None
        stages: list[WorkflowStageStatus] = []
        for sd in stages_data:
            if not isinstance(sd, dict):
                continue
            stages.append(WorkflowStageStatus(
                stage=sd.get("stage", ""),
                config=sd.get("config", ""),
                status=sd.get("status", "pending"),
                run_id=sd.get("run_id"),
                started_at=sd.get("started_at", 0.0) or 0.0,
                finished_at=sd.get("finished_at", 0.0) or 0.0,
                error=sd.get("error"),
            ))
        return WorkflowRunHandle(
            run_id=state.run_id,
            name=params.get("name", ""),
            status="running",
            started_at=state.started_at,
            finished_at=0.0,
            error=None,
            stages=stages,
            config_path=state.config_path,
        )

    @staticmethod
    def _first_unfinished_stage(handle: WorkflowRunHandle) -> str | None:
        for s in handle.stages:
            if s.status not in ("done",):
                return s.stage
        return None

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

    def _orchestrate(self, handle: WorkflowRunHandle, *, resume: bool = False) -> None:
        """Drive the workflow through its stages, one at a time.

        ``resume=True`` is used after a reattach on server startup: we
        skip stages already marked ``done``, re-poll a stage that was
        ``running`` when the server died (its child may have finished
        already), and finalise earlier if an earlier stage was marked
        failed/cancelled.
        """
        handle.push_event({
            "event": "workflow_resumed" if resume else "workflow_started",
            "name": handle.name,
            "n_stages": len(handle.stages),
        })

        for i, stage in enumerate(handle.stages):
            # Resume: skip already-finished stages, handle pre-failed
            # stages as terminal.
            if resume:
                if stage.status == "done":
                    continue
                if stage.status in ("failed", "cancelled", "lost"):
                    self._finalize(
                        handle,
                        "failed" if stage.status != "cancelled" else "cancelled",
                        error=f"{stage.stage} {stage.status}: "
                              f"{stage.error or 'stage was terminal before restart'}",
                    )
                    return

            if handle._cancel.is_set():
                stage.status = "cancelled"
                handle.push_event({"event": "stage_cancelled", "stage": stage.stage})
                self._finalize(handle, "cancelled", error="cancelled before start")
                return

            # Resume path with an existing child run_id: the stage was
            # running when the server died. Don't re-launch; just
            # re-poll. The stage's started_at stays at its original
            # pre-restart value.
            child_run_id: str | None = None
            if resume and stage.status == "running" and stage.run_id:
                child_run_id = stage.run_id
                handle.push_event({
                    "event": "stage_reattached",
                    "stage": stage.stage,
                    "index": i,
                    "run_id": child_run_id,
                })
            else:
                # Fresh launch (either a new workflow or a pending
                # stage on resume).
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
        """Return {status, error} from the child manager's active set.

        Falls back to the persistent registry when the handle isn't in
        ``active_runs`` — important after a server restart, where a
        child run that completed during the outage has a state.json
        with the final status but is never rehydrated into
        ``active_runs`` (the per-stage reattach only picks up runs
        whose PID is still alive).
        """
        if stage == "convert":
            # Batch?
            batch_handle = getattr(mgr, "active_batches", {}).get(child_run_id)
            if batch_handle is not None:
                if batch_handle.status in ("done", "failed", "cancelled"):
                    counts = batch_handle.summary.get("counts", {})
                    if counts.get("failed", 0) > 0:
                        return {"status": "failed", "error": f"{counts['failed']} job(s) failed"}
                    return {"status": batch_handle.status}
                return {"status": "running"}
            # Single run
            h = getattr(mgr, "active_runs", {}).get(child_run_id)
            if h is not None:
                return {"status": h.status, "error": h.error}
            return self._read_child_status_from_registry(child_run_id)

        h = getattr(mgr, "active_runs", {}).get(child_run_id)
        if h is not None:
            return {"status": h.status, "error": getattr(h, "error", None)}
        return self._read_child_status_from_registry(child_run_id)

    def _read_child_status_from_registry(self, child_run_id: str) -> dict | None:
        """Load a child's state.json from the shared run registry.

        Returns None if no state file exists — the workflow orchestrator
        interprets that as "child vanished, probably done & cleaned up"
        and moves on.
        """
        state = self.registry.load(child_run_id)
        if state is None:
            return None
        return {"status": state.status, "error": state.error}

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

    def delete_run(self, run_id: str) -> dict:
        """Delete a finished workflow run and cascade to its stage runs.

        Refuses while the workflow itself is still running. Each stage's
        child run (if any) is deleted via that stage's manager, which
        applies its own per-stage output-cleanup rules. Then the
        workflow's own registry dir is removed.
        """
        handle = self.active_runs.get(run_id)
        status = handle.status if handle else None
        state = self.registry.load(run_id)
        if status is None and state is not None:
            status = state.status
        if status == "running":
            return {"deleted": False, "reason": "workflow is still running; cancel first"}
        if state is None and handle is None:
            return {"deleted": False, "reason": "workflow not found"}

        stage_results: list[dict] = []
        # Collect child runs: prefer the in-memory handle (has full
        # WorkflowStageStatus objects); fall back to state.params which
        # stores a list of dicts per stage.
        if handle is not None:
            stage_iter = [
                {"stage": s.stage, "run_id": s.run_id}
                for s in handle.stages
            ]
        else:
            stage_iter = (state.params or {}).get("stages", []) if state else []

        for sdata in stage_iter:
            child_stage = sdata.get("stage")
            child_run_id = sdata.get("run_id")
            if not child_stage or not child_run_id:
                continue
            mgr = self.stage_managers.get(child_stage)
            if mgr is None or not hasattr(mgr, "delete_run"):
                stage_results.append({
                    "stage": child_stage,
                    "run_id": child_run_id,
                    "deleted": False,
                    "reason": "manager not available",
                })
                continue
            try:
                r = mgr.delete_run(child_run_id)
            except Exception as e:
                r = {"deleted": False, "reason": str(e)}
            stage_results.append({
                "stage": child_stage,
                "run_id": child_run_id,
                **r,
            })

        self.active_runs.pop(run_id, None)
        existed = self.registry.delete(run_id)
        return {
            "deleted": True if (existed or stage_results) else False,
            "stage_results": stage_results,
        }
