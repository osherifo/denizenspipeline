"""PreprocRunManager — launch, list, cancel, resume and restart pipeline runs.

Every run is a detached ``pipeline_runner_cli`` subprocess registered in
the shared :class:`~fmriflow.server.services.run_registry.RunRegistry`
(``kind="preproc"``). The subprocess owns the nipype work dir and writes
``events.jsonl`` (node + run events), ``preproc_manifest.json`` and the
terminal status into ``state.json``; this manager only reads those.

Resume vs restart: a run that died (server restart, kill) shows as
``lost``. *Resume* launches a new run with the same job — nipype's
per-node hashing skips every node that already completed. *Restart*
does the same with ``use_cache=False``. Neither happens silently.
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

import yaml

from fmriflow.preproc.graph import Pipeline, PipelineRunRequest
from fmriflow.preproc.node_registry import NodeRegistry
from fmriflow.preproc.pipeline_runner import workflow_name
from fmriflow.server.services.pipeline_store import PipelineStore, is_legacy_preproc_config
from fmriflow.server.services.run_registry import RunRegistry, RunStateFile

logger = logging.getLogger(__name__)

_CLI_MODULE = "fmriflow.preproc.pipeline_runner_cli"
RUN_KIND = "preproc"

LEGACY_HINT = (
    "This preproc config uses the old 'backend' / 'backend_params' shape. "
    "Convert it with `fmriflow preproc migrate` and reference the resulting "
    "pipeline as `preproc: {pipeline: <name>, ...}`."
)


class PreprocRunManager:
    GRACE_PERIOD_S = 5.0

    def __init__(
        self,
        run_registry: RunRegistry | None = None,
        pipeline_store: PipelineStore | None = None,
        node_registry: NodeRegistry | None = None,
    ) -> None:
        self.registry = run_registry or RunRegistry()
        self.pipeline_store = pipeline_store or PipelineStore()
        self.node_registry = node_registry or NodeRegistry().discover()

    # ── launch ────────────────────────────────────────────────────

    def validate(self, pipeline: Pipeline, request: PipelineRunRequest) -> list[str]:
        from fmriflow.preproc.pipeline_runner import PipelineRunner
        return PipelineRunner(self.node_registry).validate(pipeline, request)

    def start_run(
        self,
        pipeline: Pipeline,
        request: PipelineRunRequest,
        *,
        pipeline_name: str | None = None,
        config_path: str | None = None,
        resumed_from: str | None = None,
    ) -> str:
        errors = self.validate(pipeline, request)
        if errors:
            raise ValueError("; ".join(errors))

        run_id = f"pp_{uuid.uuid4().hex[:12]}"
        backend_node = pipeline.manifest.get("backend_node")
        backend = pipeline.node(backend_node).type if backend_node and pipeline.has_node(backend_node) else "pipeline"
        state = RunStateFile(
            run_id=run_id,
            kind=RUN_KIND,
            backend=backend,
            subject=request.subject,
            status="running",
            started_at=time.time(),
            config_path=config_path,
            params={
                "pipeline": pipeline_name or pipeline.name,
                "nodes": [{"id": n.id, "type": n.type, "kind": n.kind} for n in pipeline.nodes],
                "n_nodes": len(pipeline.nodes),
                "use_cache": request.use_cache,
                "rerun_from": list(request.rerun_from),
                "plugin": request.plugin,
                "output_dir": request.output_dir,
                "work_dir": request.work_dir or str(Path(request.output_dir) / "work"),
                "workflow": workflow_name(pipeline, request),
                "resumed_from": resumed_from,
            },
        )
        run_dir = self.registry.register(state)
        job_path = run_dir / "job.json"
        job_path.write_text(json.dumps(
            {"pipeline": pipeline.to_dict(), "request": request.to_dict()}, indent=2, default=str,
        ))
        proc = self._spawn(run_id, job_path, self.registry.stdout_path(run_id))
        state.pid = proc.pid
        try:
            state.pgid = os.getpgid(proc.pid)
        except OSError:
            state.pgid = proc.pid
        self.registry.update(state)
        logger.info("pipeline run %s spawned (pid=%s, pipeline=%s, subject=%s)",
                    run_id, proc.pid, state.params["pipeline"], request.subject)
        return run_id

    def _spawn(self, run_id: str, job_path: Path, log_path: Path) -> subprocess.Popen:
        cmd = [
            sys.executable, "-m", _CLI_MODULE,
            "--run-id", run_id, "--config", str(job_path),
            "--registry-root", str(self.registry.root),
        ]
        log_path.parent.mkdir(parents=True, exist_ok=True)
        return subprocess.Popen(
            cmd, stdout=open(log_path, "ab"), stderr=subprocess.STDOUT, start_new_session=True,
        )

    def start_run_by_name(self, name: str, request: PipelineRunRequest) -> str:
        pipeline = self.pipeline_store.load(name)
        return self.start_run(pipeline, request, pipeline_name=name)

    def start_run_from_config_file(self, config_path: str, overrides: dict | None = None) -> str:
        """Workflow-stage entry: a YAML with a ``preproc:`` section.

        ``preproc: {pipeline: <name> | <inline pipeline dict>, subject, output_dir,
        bids_dir, derivatives_dir, work_dir, dataset, task, sessions, inputs,
        plugin, n_procs, use_cache, params_override}``.

        The old ``backend`` / ``backend_params`` shape is rejected with a
        pointer at ``fmriflow preproc migrate``.
        """
        path = Path(config_path)
        if not path.is_file():
            raise FileNotFoundError(f"Preproc config not found: {path}")
        data = yaml.safe_load(path.read_text()) or {}
        section = data.get("preproc") if isinstance(data.get("preproc"), dict) else data
        if not isinstance(section, dict):
            raise ValueError(f"Config '{path.name}' has no 'preproc:' section")
        if is_legacy_preproc_config(section):
            raise ValueError(f"{path.name}: {LEGACY_HINT}")
        section = dict(section)
        if overrides:
            section.update({k: v for k, v in overrides.items() if v is not None})

        ref = section.pop("pipeline", None)
        if isinstance(ref, dict):
            pipeline = Pipeline.from_dict(ref)
            pipeline_name = pipeline.name
        elif isinstance(ref, str) and ref:
            pipeline = self.pipeline_store.load(ref)
            pipeline_name = ref
        elif "nodes" in section:
            pipeline = Pipeline.from_dict(section)
            pipeline_name = pipeline.name
            for k in ("nodes", "edges", "inputs", "outputs", "manifest", "schema_version", "name", "description"):
                section.pop(k, None)
        else:
            raise ValueError(f"{path.name}: preproc section needs 'pipeline: <name>' (or an inline pipeline)")

        missing = [k for k in ("subject", "output_dir") if not section.get(k)]
        if missing:
            raise ValueError(f"{path.name}: preproc config missing required fields: {', '.join(missing)}")
        request = PipelineRunRequest.from_dict(section)
        return self.start_run(pipeline, request, pipeline_name=pipeline_name, config_path=str(path.resolve()))

    # ── resume / restart ──────────────────────────────────────────

    def _job(self, run_id: str) -> tuple[Pipeline, PipelineRunRequest, RunStateFile]:
        state = self.registry.load(run_id)
        if state is None:
            raise KeyError(f"unknown run {run_id!r}")
        job = json.loads((self.registry.run_dir(run_id) / "job.json").read_text())
        return Pipeline.from_dict(job["pipeline"]), PipelineRunRequest.from_dict(job["request"]), state

    def resume_run(self, run_id: str) -> str:
        """Re-launch the same job; nipype's cache skips finished nodes."""
        pipeline, request, state = self._job(run_id)
        if self._live_status(state) == "running":
            raise ValueError(f"run {run_id} is still running")
        request.use_cache = True
        request.rerun_from = []
        return self.start_run(pipeline, request, pipeline_name=state.params.get("pipeline"),
                              config_path=state.config_path, resumed_from=run_id)

    def restart_run(self, run_id: str) -> str:
        """Re-launch the same job from scratch (``use_cache=False``)."""
        pipeline, request, state = self._job(run_id)
        if self._live_status(state) == "running":
            raise ValueError(f"run {run_id} is still running")
        request.use_cache = False
        request.rerun_from = []
        return self.start_run(pipeline, request, pipeline_name=state.params.get("pipeline"),
                              config_path=state.config_path, resumed_from=run_id)

    # ── query ─────────────────────────────────────────────────────

    def _live_status(self, state: RunStateFile) -> str:
        if state.status == "running" and not self.registry.pid_alive(state.pid):
            return "lost"
        return state.status

    def get_run(self, run_id: str) -> dict | None:
        state = self.registry.load(run_id)
        if state is None or state.kind != RUN_KIND:
            return None
        return self._summary(state)

    def list_runs(self) -> list[dict]:
        return [self._summary(s) for s in self.registry.list_all() if s.kind == RUN_KIND]

    def run_dir(self, run_id: str) -> Path:
        return self.registry.run_dir(run_id)

    def events_path(self, run_id: str) -> Path:
        return self.registry.run_dir(run_id) / "events.jsonl"

    def job(self, run_id: str) -> dict | None:
        path = self.registry.run_dir(run_id) / "job.json"
        return json.loads(path.read_text()) if path.is_file() else None

    def checkpoints_path(self, run_id: str) -> Path:
        return self.registry.run_dir(run_id) / "checkpoints.jsonl"

    def checkpoints(self, run_id: str) -> list[dict]:
        from fmriflow.preproc.checkpoints import read_checkpoints
        return [cp.to_dict() for cp in read_checkpoints(self.checkpoints_path(run_id))]

    def checkpoint_summary(self, run_id: str) -> dict:
        from fmriflow.preproc.checkpoints import read_checkpoints, worst_verdict
        cps = read_checkpoints(self.checkpoints_path(run_id))
        counts: dict[str, int] = {"ok": 0, "suspicious": 0, "bad": 0, "unknown": 0}
        for cp in cps:
            counts[cp.verdict] = counts.get(cp.verdict, 0) + 1
        return {"n": len(cps), "counts": counts, "worst": worst_verdict([cp.verdict for cp in cps]) if cps else None}

    def nipype_status(self, run_id: str) -> dict:
        from fmriflow.preproc.nipype_log import parse_nipype_events_file, reconcile_with_run_state

        state = self.registry.load(run_id)
        block = parse_nipype_events_file(self.events_path(run_id))
        if state is not None:
            block = reconcile_with_run_state(block, run_status=self._live_status(state))
        return block.to_dict()

    def _summary(self, state: RunStateFile) -> dict:
        params = state.params or {}
        return {
            "run_id": state.run_id,
            "kind": state.kind,
            "backend": state.backend,
            "subject": state.subject,
            "status": self._live_status(state),
            "pid": state.pid,
            "started_at": state.started_at,
            "finished_at": state.finished_at,
            "manifest_path": state.manifest_path,
            "error": state.error,
            "pipeline": params.get("pipeline"),
            "nodes": params.get("nodes", []),
            "n_nodes": params.get("n_nodes", 0),
            "work_dir": params.get("work_dir"),
            "workflow": params.get("workflow"),
            "output_dir": params.get("output_dir"),
            "use_cache": params.get("use_cache", True),
            "resumed_from": params.get("resumed_from"),
            "config_path": state.config_path,
            "result": state.result,
            "checkpoints": self.checkpoint_summary(state.run_id),
        }

    # ── cancel / delete / reconcile ───────────────────────────────

    def cancel_run(self, run_id: str) -> dict:
        state = self.registry.load(run_id)
        if state is None:
            return {"cancelled": False, "reason": "unknown run_id"}
        if state.status != "running":
            return {"cancelled": False, "reason": f"status is {state.status}"}
        pgid = state.pgid or state.pid
        if not pgid:
            return {"cancelled": False, "reason": "no pid recorded"}
        # Record the cancel *before* signalling: the runner re-reads state.json
        # on its way out and must not overwrite "cancelled" with "failed".
        state.status = "cancelled"
        state.finished_at = time.time()
        self.registry.update(state)
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            state.error = "process already gone at cancel time"
            self.registry.update(state)
            return {"cancelled": True, "reason": "process already exited"}
        except Exception as e:
            state.status = "running"
            state.finished_at = 0.0
            self.registry.update(state)
            return {"cancelled": False, "reason": str(e)}

        recorded_pid = state.pid

        def _grace_kill() -> None:
            time.sleep(self.GRACE_PERIOD_S)
            if RunRegistry.pid_alive(recorded_pid):
                try:
                    os.killpg(pgid, signal.SIGKILL)
                except Exception:
                    logger.warning("Failed to SIGKILL pgid=%s", pgid, exc_info=True)

        threading.Thread(target=_grace_kill, daemon=True).start()
        return {"cancelled": True}

    def delete_run(self, run_id: str) -> bool:
        state = self.registry.load(run_id)
        if state is None or state.kind != RUN_KIND:
            return False
        if self._live_status(state) == "running":
            raise ValueError("cannot delete a running run; cancel it first")
        return self.registry.delete(run_id)

    def scan_for_orphans(self) -> int:
        count = 0
        for state in self.registry.list_all():
            if state.kind != RUN_KIND or state.status != "running":
                continue
            if not self.registry.pid_alive(state.pid):
                self.registry.mark_lost(state, reason="Server restarted while the pipeline run was running.")
                count += 1
        if count:
            logger.warning("Reconciled %d orphaned pipeline run(s).", count)
        return count
