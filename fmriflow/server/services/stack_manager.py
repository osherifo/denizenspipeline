"""StackManager — lifecycle for detached PreprocStack runs.

Mirrors the existing ``PreprocManager`` shape but is much thinner
because ``StackRunner`` already orchestrates the whole pipeline.
The manager's job is:

- Persist the launch request (stack + run_config) to disk so the
  detached subprocess can read it back.
- Spawn ``python -m fmriflow.preproc.stack_runner_cli`` with
  ``start_new_session=True`` so the job survives a server restart.
- Track liveness via ``RunRegistry`` (one ``RunStateFile`` per run).
- On startup, scan for orphans: runs whose ``state.json`` says
  ``running`` but whose pid is gone get marked ``lost``.

Cancel / live event streaming live in Phase 5b — Phase 5 ships
poll-based status. ``GET .../status`` returns whatever the
registry currently has on disk.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from fmriflow.preproc.stack import PreprocStack
from fmriflow.server.services.run_registry import RunRegistry, RunStateFile

logger = logging.getLogger(__name__)


# Defensive constant — kept aligned with the CLI shim's expected
# command-line. If the shim changes, update both.
_CLI_MODULE = "fmriflow.preproc.stack_runner_cli"


class StackManager:
    """Owns the lifecycle of detached stack runs.

    Construction is cheap; the manager doesn't hold any per-run
    state in memory — everything is round-tripped through the
    ``RunRegistry`` so reattach works after a restart.
    """

    def __init__(self, run_registry: RunRegistry | None = None) -> None:
        self.registry = run_registry or RunRegistry()

    # ── Lifecycle ─────────────────────────────────────────────────

    def start_run(
        self,
        stack: PreprocStack,
        run_config: dict[str, Any],
        *,
        use_cache: bool = True,
    ) -> str:
        """Spawn a detached subprocess to execute ``stack``.

        ``run_config`` is a dict matching ``StackRunConfig`` (the CLI
        shim parses it). Returns the new run_id.

        Validates the stack's bootstrap kind + that the subject and
        output_dir are set before spawning; mis-configurations should
        surface as 400 from the route, not as a half-spawned
        subprocess that immediately fails.
        """
        self._validate_request(stack, run_config)

        run_id = f"stack_{uuid.uuid4().hex[:12]}"

        # Register state up front so the subprocess can update it.
        state = RunStateFile(
            run_id=run_id,
            kind="stack",
            backend=stack.bootstrap.kind,
            subject=str(run_config["subject"]),
            status="running",
            started_at=time.time(),
            params={
                "bootstrap": {
                    "kind": stack.bootstrap.kind,
                    "workflow": stack.bootstrap.workflow,
                },
                "n_transforms": len(stack.transforms),
                "transforms": [t.name for t in stack.transforms],
                "use_cache": use_cache,
            },
        )
        run_dir = self.registry.register(state)

        # Write the job-config JSON that the CLI shim will read.
        job_path = run_dir / "job.json"
        job_path.write_text(
            json.dumps(
                {
                    "stack": stack.to_dict(),
                    "run_config": dict(run_config),
                    "use_cache": use_cache,
                },
                indent=2,
                default=str,
            )
        )

        # Spawn detached.
        log_path = self.registry.stdout_path(run_id)
        proc = self._spawn(run_id, job_path, log_path)
        state.pid = proc.pid
        try:
            state.pgid = os.getpgid(proc.pid)
        except OSError:
            state.pgid = proc.pid
        self.registry.update(state)

        logger.info(
            "Stack run %s spawned (pid=%s, kind=%s, subject=%s)",
            run_id, proc.pid, stack.bootstrap.kind, run_config.get("subject"),
        )
        return run_id

    def _spawn(
        self, run_id: str, job_path: Path, log_path: Path,
    ) -> subprocess.Popen:
        cmd = [
            sys.executable, "-m", _CLI_MODULE,
            "--run-id", run_id,
            "--config", str(job_path),
            # The shim creates its own RunRegistry — point it at the
            # same root we use so state.json updates land in the
            # registry this manager reads from.
            "--registry-root", str(self.registry.root),
        ]
        log_path.parent.mkdir(parents=True, exist_ok=True)
        # ``start_new_session=True`` puts the child in its own
        # process group + session so it survives the parent dying.
        return subprocess.Popen(
            cmd,
            stdout=open(log_path, "ab"),
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    def _validate_request(
        self, stack: PreprocStack, run_config: dict[str, Any],
    ) -> None:
        missing = [k for k in ("subject", "output_dir") if not run_config.get(k)]
        if missing:
            raise ValueError(
                f"run_config missing required fields: {', '.join(missing)}"
            )
        # Stack shape itself is dataclass-validated; semantic
        # validation (workflow registered, transforms registered,
        # preflight) happens inside StackRunner._validate at run-time.
        # We surface those as failed runs, not 400s, because they may
        # depend on the subprocess's environment.

    # ── Read-side ────────────────────────────────────────────────

    def get_run(self, run_id: str) -> dict | None:
        """Return a JSON-able summary of a single run, or None if not found."""
        state = self.registry.load(run_id)
        if state is None:
            return None
        # Reconcile liveness: if state says running but pid is gone,
        # surface as 'lost' to the caller (but don't mutate state.json
        # here — let the periodic sweep do it).
        live = state.status
        if state.status == "running" and not self.registry.pid_alive(state.pid):
            live = "lost"
        return self._summary(state, live_status=live)

    def list_runs(self) -> list[dict]:
        out: list[dict] = []
        for state in self.registry.list_all():
            if state.kind != "stack":
                continue
            live = state.status
            if state.status == "running" and not self.registry.pid_alive(state.pid):
                live = "lost"
            out.append(self._summary(state, live_status=live))
        return out

    def get_manifest_path(self, run_id: str) -> Path | None:
        """Return the final stack manifest path if the run is done."""
        state = self.registry.load(run_id)
        if state is None or not state.manifest_path:
            return None
        path = Path(state.manifest_path)
        return path if path.is_file() else None

    # ── Cancel ───────────────────────────────────────────────────

    GRACE_PERIOD_S = 5.0

    def cancel_run(self, run_id: str) -> dict:
        """Terminate a running stack subprocess. SIGTERM, then SIGKILL
        after a grace period if still alive.

        Returns a small dict describing the outcome:

            {"cancelled": True}
            {"cancelled": False, "reason": "<why>"}
        """
        state = self.registry.load(run_id)
        if state is None:
            return {"cancelled": False, "reason": "unknown run_id"}
        if state.status != "running":
            return {"cancelled": False, "reason": f"status is {state.status}"}
        pgid = state.pgid or state.pid
        if not pgid:
            return {"cancelled": False, "reason": "no pid recorded"}

        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            # Already gone — reconcile state to "failed" so we don't
            # leave a stale "running".
            state.status = "failed"
            state.error = "process already gone at cancel time"
            state.finished_at = time.time()
            self.registry.update(state)
            return {"cancelled": True, "reason": "process already exited"}
        except Exception as e:
            return {"cancelled": False, "reason": str(e)}

        # Grace period: if the subprocess hasn't shut down on its own
        # within GRACE_PERIOD_S, SIGKILL the whole process group.
        recorded_pid = state.pid

        def _grace_kill() -> None:
            time.sleep(self.GRACE_PERIOD_S)
            if RunRegistry.pid_alive(recorded_pid):
                try:
                    os.killpg(pgid, signal.SIGKILL)
                except Exception:
                    logger.warning(
                        "Failed to SIGKILL pgid=%s after grace period", pgid,
                        exc_info=True,
                    )

        threading.Thread(target=_grace_kill, daemon=True).start()

        state.status = "cancelled"
        state.finished_at = time.time()
        self.registry.update(state)
        logger.info("Cancelled stack run %s (pgid=%s).", run_id, pgid)
        return {"cancelled": True}

    # ── Reconciliation ───────────────────────────────────────────

    def scan_for_orphans(self) -> int:
        """Find runs marked ``running`` whose pid is gone; mark them
        ``lost`` and persist. Call this once at server startup.
        Returns the count reconciled.
        """
        count = 0
        for state in self.registry.list_all():
            if state.kind != "stack":
                continue
            if state.status != "running":
                continue
            if not self.registry.pid_alive(state.pid):
                self.registry.mark_lost(
                    state,
                    reason="Server restarted while stack run was running.",
                )
                count += 1
        if count:
            logger.warning(
                "Reconciled %d orphaned stack runs (server restarted mid-run).",
                count,
            )
        return count

    # ── Helpers ──────────────────────────────────────────────────

    def _summary(self, state: RunStateFile, *, live_status: str) -> dict:
        return {
            "run_id": state.run_id,
            "kind": state.kind,
            "backend": state.backend,
            "subject": state.subject,
            "status": live_status,
            "pid": state.pid,
            "started_at": state.started_at,
            "finished_at": state.finished_at,
            "manifest_path": state.manifest_path,
            "error": state.error,
            "params": state.params,
            "result": state.result,
        }
