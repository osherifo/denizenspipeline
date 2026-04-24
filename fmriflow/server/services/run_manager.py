"""RunManager — launches and tracks analysis pipeline runs.

Runs spawn the ``fmriflow run <config.yaml>`` CLI as a detached subprocess
(``start_new_session=True``) with stdout+stderr captured to a log file
under ``~/.fmriflow/runs/{run_id}/stdout.log`` and a sidecar
``state.json``. They survive server restarts: on startup the manager
scans the registry and reattaches any live pipeline PIDs.

Tradeoff: structured stage events that used to flow via UICaptureProxy
are not emitted to the WebSocket during detached runs (the subprocess
can't reach the parent's in-memory queue). The live log stream from the
tailer is still there, and on completion the stage timeline is loaded
back from ``{output_dir}/run_summary.json``.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess as _subprocess
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from fmriflow.server.services.run_registry import RunRegistry, RunStateFile

logger = logging.getLogger(__name__)


@dataclass
class RunHandle:
    """A single analysis pipeline run.

    Detach-reattach bookkeeping lives alongside the legacy fields; the
    WebSocket endpoint treats ``log`` events the same way the preproc /
    convert / autoflatten streams do.
    """

    run_id: str
    config: dict
    config_path: str | None = None
    status: str = 'pending'              # pending | running | done | failed | cancelled | lost
    error: str | None = None
    events: list[dict] = field(default_factory=list)
    _pending: list[dict] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    # Detach-reattach bookkeeping
    pid: int | None = None
    pgid: int | None = None
    log_path: str | None = None
    events_path: str | None = None
    output_dir: str | None = None
    is_reattached: bool = False
    started_at: float = 0.0
    finished_at: float = 0.0

    # Path to a temp YAML we wrote for subprocess consumption (cleanup after run).
    _temp_config_path: str | None = None

    def push_event(self, event: dict) -> None:
        event.setdefault('timestamp', time.time())
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
            'run_id': self.run_id,
            'status': self.status,
            'pid': self.pid,
            'started_at': self.started_at,
            'finished_at': self.finished_at,
            'is_reattached': self.is_reattached,
            'error': self.error,
            'config_path': self.config_path,
            'output_dir': self.output_dir,
            'log_path': self.log_path,
            'events_path': self.events_path,
        }


class RunManager:
    """Manages background pipeline runs as detached subprocesses."""

    def __init__(self, registry: RunRegistry | None = None):
        self.active_runs: dict[str, RunHandle] = {}
        self.registry = registry or RunRegistry()
        try:
            self._reattach_active_runs()
        except Exception:
            logger.warning("Failed to scan run registry on startup", exc_info=True)

    # ── Launch ──────────────────────────────────────────────────────

    def start_run(self, config: dict) -> str:
        """Launch a pipeline run from a config dict.

        The dict is written to a temp YAML so the CLI subprocess can
        consume it; the temp file is cleaned up when the run finishes
        (or the server dies — temp files are tracked in ``TMPDIR``).
        """
        if not isinstance(config, dict) or not config:
            raise ValueError("start_run requires a non-empty config dict")

        run_id = uuid.uuid4().hex[:12]
        # Write dict → temp YAML that the CLI can load.
        tmp = tempfile.NamedTemporaryFile(
            mode='w', suffix=f"_{run_id}.yaml", delete=False,
        )
        yaml.safe_dump(config, tmp, sort_keys=False, allow_unicode=True)
        tmp.close()

        handle = self._register_handle(
            run_id=run_id,
            config=config,
            config_path=tmp.name,
            temp_config_path=tmp.name,
        )
        self._spawn_and_track(handle)
        logger.info("Started run %s (temp config %s)", run_id, tmp.name)
        return run_id

    def start_run_from_config(
        self,
        config_path: str,
        overrides: dict | None = None,
    ) -> str:
        """Launch a pipeline run from a YAML config file.

        If ``overrides`` is provided and non-empty, we write a merged
        temp YAML so the CLI picks up the overrides; otherwise we pass
        the original path through so the run log shows the real
        filename.
        """
        run_id = uuid.uuid4().hex[:12]
        effective_path = config_path
        temp_path: str | None = None

        if overrides:
            with open(config_path) as f:
                base = yaml.safe_load(f) or {}
            for k, v in overrides.items():
                if v is not None:
                    base[k] = v
            tmp = tempfile.NamedTemporaryFile(
                mode='w', suffix=f"_{run_id}.yaml", delete=False,
            )
            yaml.safe_dump(base, tmp, sort_keys=False, allow_unicode=True)
            tmp.close()
            effective_path = tmp.name
            temp_path = tmp.name

        # Load config for bookkeeping (output_dir extraction + config_snapshot parity).
        with open(effective_path) as f:
            config = yaml.safe_load(f) or {}

        handle = self._register_handle(
            run_id=run_id,
            config=config,
            config_path=effective_path,
            temp_config_path=temp_path,
        )
        self._spawn_and_track(handle)
        logger.info("Started run %s from config %s", run_id, effective_path)
        return run_id

    # ── Registry + spawn helpers ────────────────────────────────────

    def _register_handle(
        self,
        *,
        run_id: str,
        config: dict,
        config_path: str,
        temp_config_path: str | None,
    ) -> RunHandle:
        now = time.time()
        output_dir = (
            (config.get('reporting') or {}).get('output_dir') or './results'
        )

        handle = RunHandle(
            run_id=run_id,
            config=config,
            config_path=config_path,
            status='running',
            started_at=now,
            output_dir=output_dir,
            _temp_config_path=temp_config_path,
        )

        state = RunStateFile(
            run_id=run_id,
            kind='run',
            backend='pipeline',
            subject=str(config.get('subject', '')),
            status='running',
            started_at=now,
            config_path=config_path,
            params={
                'config_path': config_path,
                'output_dir': output_dir,
                'experiment': config.get('experiment'),
            },
        )
        self.registry.register(state)
        handle.log_path = state.stdout_log
        self.active_runs[run_id] = handle
        return handle

    def _spawn_and_track(self, handle: RunHandle) -> None:
        thread = threading.Thread(
            target=self._execute,
            args=(handle,),
            daemon=True,
            name=f"run-{handle.run_id}",
        )
        thread.start()

    def _execute(self, handle: RunHandle) -> None:
        """Spawn the CLI as a detached child and drive its log."""
        log_path = Path(handle.log_path) if handle.log_path else None
        events_path = (log_path.parent / "events.jsonl") if log_path else None

        try:
            cmd = [
                sys.executable, "-u", "-m", "fmriflow.cli",
                "run", handle.config_path,
            ]
            logger.info("Running pipeline: %s", " ".join(cmd))

            handle.push_event({
                'event': 'started',
                'message': f"Starting pipeline for {handle.config.get('experiment', '?')}",
            })

            # Pass an events file so the subprocess can emit per-stage
            # transitions (stimuli/responses/features/prepare/model/
            # analyze/report) for the workflow graph and UI.
            child_env = os.environ.copy()
            if events_path is not None:
                events_path.touch()
                child_env["FMRIFLOW_EVENTS_FILE"] = str(events_path)
                handle.events_path = str(events_path)
                self._persist_state(handle)

            if log_path is not None:
                log_fh = open(log_path, "w", buffering=1)
            log_fh = None
            tailer = None
            try:
                if log_path is not None:
                    log_fh = open(log_path, "w", buffering=1)
                    proc = _subprocess.Popen(
                        cmd,
                        stdout=log_fh,
                        stderr=_subprocess.STDOUT,
                        text=True,
                        start_new_session=True,
                    )
                else:
                    proc = _subprocess.Popen(
                        cmd, stdout=_subprocess.PIPE, stderr=_subprocess.STDOUT, text=True,
                    )

                handle.pid = proc.pid
                try:
                    handle.pgid = os.getpgid(proc.pid)
                except OSError:
                    handle.pgid = proc.pid
                self._persist_state(handle)

                if log_path is not None:
                    tailer = _RunLogTailer(
                        log_path, handle, stop_when=lambda: proc.poll() is not None,
                    )
                    tailer.start()

                proc.wait()
                self._finalize_from_output(handle, proc.returncode)
            finally:
                if tailer is not None:
                    tailer.stop_and_join()
                if log_fh is not None:
                    log_fh.close()

        except Exception as e:
            import traceback as _tb
            tb_text = _tb.format_exc()
            handle.status = 'failed'
            handle.error = f"{type(e).__name__}: {e}"
            handle.finished_at = time.time()
            handle.push_event({
                'event': 'run_failed',
                'error': handle.error,
                'traceback': tb_text,
                'elapsed': handle.finished_at - handle.started_at,
            })
            if handle.log_path:
                try:
                    with open(handle.log_path, 'a') as _lf:
                        _lf.write('\n\n=== wrapper traceback ===\n')
                        _lf.write(tb_text)
                except Exception:
                    pass
            logger.error("Run %s failed: %s", handle.run_id, e, exc_info=True)

        finally:
            self._persist_state(handle)
            # Clean up the temp YAML if we wrote one.
            if handle._temp_config_path:
                try:
                    os.unlink(handle._temp_config_path)
                except Exception:
                    pass

    def _finalize_from_output(self, handle: RunHandle, returncode: int) -> None:
        """Inspect {output_dir}/run_summary.json to determine final status."""
        summary_path = (
            Path(handle.output_dir) / 'run_summary.json'
            if handle.output_dir else None
        )
        summary: dict | None = None
        if summary_path and summary_path.is_file():
            try:
                summary = json.loads(summary_path.read_text())
            except Exception:
                summary = None

        now = time.time()
        handle.finished_at = now

        if returncode == 0 and summary is not None:
            handle.status = 'done'
            total_elapsed = summary.get('total_elapsed_s', now - handle.started_at)
            handle.push_event({
                'event': 'run_done',
                'total_elapsed': total_elapsed,
                'summary_path': str(summary_path),
            })
        elif returncode == 0:
            # Exited 0 but no summary — should not happen with current CLI.
            handle.status = 'failed'
            handle.error = 'pipeline exited 0 but produced no run_summary.json'
            handle.push_event({
                'event': 'run_failed',
                'error': handle.error,
                'elapsed': now - handle.started_at,
            })
        else:
            handle.status = 'failed'
            # Pull a terse reason from the summary if present.
            if summary and summary.get('status') == 'failed':
                stages = summary.get('stages', [])
                failed_stage = next(
                    (s for s in stages if s.get('status') == 'failed'),
                    None,
                )
                if failed_stage:
                    handle.error = (
                        f"{failed_stage.get('name')}: "
                        f"{failed_stage.get('detail') or 'stage failed'}"
                    )
            if not handle.error:
                handle.error = f"pipeline exited with code {returncode}"
            handle.push_event({
                'event': 'run_failed',
                'error': handle.error,
                'elapsed': now - handle.started_at,
            })

    # ── Registry / reattach / cancel ────────────────────────────────

    def _persist_state(self, handle: RunHandle) -> None:
        state = RunStateFile(
            run_id=handle.run_id,
            kind='run',
            backend='pipeline',
            subject=str(handle.config.get('subject', '')),
            status=handle.status,
            pid=handle.pid,
            pgid=handle.pgid,
            started_at=handle.started_at,
            finished_at=handle.finished_at,
            stdout_log=handle.log_path or '',
            config_path=handle.config_path,
            params={
                'config_path': handle.config_path,
                'output_dir': handle.output_dir,
                'experiment': handle.config.get('experiment'),
                'events_path': handle.events_path,
            },
            error=handle.error,
        )
        self.registry.update(state)

    def _reattach_active_runs(self) -> None:
        for state in self.registry.list_active():
            if state.kind != 'run':
                continue
            if not RunRegistry.pid_alive(state.pid):
                self.registry.mark_lost(state, 'server_lost_track')
                continue

            params = state.params or {}
            config = {}
            cfg_path = params.get('config_path') or state.config_path
            if cfg_path and Path(cfg_path).is_file():
                try:
                    with open(cfg_path) as f:
                        config = yaml.safe_load(f) or {}
                except Exception:
                    config = {}

            handle = RunHandle(
                run_id=state.run_id,
                config=config,
                config_path=cfg_path,
                status='running',
                started_at=state.started_at,
                pid=state.pid,
                pgid=state.pgid,
                log_path=state.stdout_log,
                events_path=params.get('events_path'),
                output_dir=params.get('output_dir'),
                is_reattached=True,
            )
            self.active_runs[state.run_id] = handle

            monitor = _RunReattachedMonitor(handle, self, state)
            thread = threading.Thread(
                target=monitor.run, daemon=True, name=f"reattach-run-{state.run_id}",
            )
            thread.start()
            logger.info(
                "Reattached to pipeline run %s (pid=%s, experiment=%s)",
                state.run_id, state.pid, (params.get('experiment') or '?'),
            )

    def list_runs(self, include_finished: bool = True) -> list[dict]:
        out: dict[str, dict] = {}
        for handle in self.active_runs.values():
            row = handle.to_summary()
            row['experiment'] = handle.config.get('experiment', '')
            row['subject'] = handle.config.get('subject', '')
            out[handle.run_id] = row
        if include_finished:
            for state in self.registry.list_all():
                if state.kind != 'run' or state.run_id in out:
                    continue
                params = state.params or {}
                out[state.run_id] = {
                    'run_id': state.run_id,
                    'status': state.status,
                    'pid': state.pid,
                    'started_at': state.started_at,
                    'finished_at': state.finished_at,
                    'is_reattached': False,
                    'error': state.error,
                    'config_path': state.config_path,
                    'output_dir': params.get('output_dir'),
                    'log_path': state.stdout_log,
                    'experiment': params.get('experiment', ''),
                    'subject': state.subject,
                }
        return sorted(out.values(), key=lambda r: r.get('started_at') or 0, reverse=True)

    def get_run_live(self, run_id: str) -> dict | None:
        handle = self.active_runs.get(run_id)
        if handle is not None:
            summary = handle.to_summary()
            summary['experiment'] = handle.config.get('experiment', '')
            summary['subject'] = handle.config.get('subject', '')
        else:
            state = self.registry.load(run_id)
            if state is None or state.kind != 'run':
                return None
            params = state.params or {}
            summary = {
                'run_id': state.run_id,
                'status': state.status,
                'pid': state.pid,
                'started_at': state.started_at,
                'finished_at': state.finished_at,
                'is_reattached': False,
                'error': state.error,
                'config_path': state.config_path,
                'output_dir': params.get('output_dir'),
                'log_path': state.stdout_log,
                'events_path': params.get('events_path'),
                'experiment': params.get('experiment', ''),
                'subject': state.subject,
            }
        log_path = summary.get('log_path')
        summary['log_tail'] = _read_tail(log_path, n=200) if log_path else ''
        summary['inner_stages'] = _parse_events_file(summary.get('events_path'))
        return summary

    def cancel_run(self, run_id: str) -> dict:
        handle = self.active_runs.get(run_id)
        if handle is None:
            return {'cancelled': False, 'reason': 'run not found in active set'}
        if handle.status != 'running':
            return {'cancelled': False, 'reason': f'status is {handle.status}'}
        pgid = handle.pgid or handle.pid
        if not pgid:
            return {'cancelled': False, 'reason': 'no pid recorded'}

        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            handle.status = 'failed'
            handle.error = 'process already gone'
            self._persist_state(handle)
            return {'cancelled': True, 'reason': 'process already exited'}
        except Exception as e:
            return {'cancelled': False, 'reason': str(e)}

        def _grace_kill():
            time.sleep(5)
            if RunRegistry.pid_alive(handle.pid):
                try:
                    os.killpg(pgid, signal.SIGKILL)
                except Exception:
                    pass
        threading.Thread(target=_grace_kill, daemon=True).start()

        handle.status = 'cancelled'
        handle.finished_at = time.time()
        handle.push_event({'event': 'cancelled', 'message': 'SIGTERM sent'})
        self._persist_state(handle)
        return {'cancelled': True}

    # ── Legacy API (kept so existing callers keep working) ──────────

    def get_status(self, run_id: str) -> dict | None:
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
        to_remove = []
        for run_id, handle in self.active_runs.items():
            if handle.status in ('done', 'failed', 'cancelled', 'lost'):
                to_remove.append(run_id)
        for run_id in to_remove:
            del self.active_runs[run_id]


# ── Log tailer + reattached monitor ─────────────────────────────────────


class _RunLogTailer(threading.Thread):
    """Reads new lines from the pipeline log file and pushes them as events."""

    def __init__(
        self,
        log_path: Path,
        handle: RunHandle,
        stop_when,
        poll_interval: float = 0.5,
    ):
        super().__init__(daemon=True, name=f"run-tail-{handle.run_id}")
        self.log_path = log_path
        self.handle = handle
        self.stop_when = stop_when
        self.poll_interval = poll_interval
        self._stop_flag = threading.Event()

    def run(self) -> None:
        deadline = time.time() + 5
        while not self.log_path.is_file() and time.time() < deadline:
            time.sleep(0.1)
        if not self.log_path.is_file():
            return
        try:
            with open(self.log_path, "r", encoding="utf-8", errors="replace") as f:
                while True:
                    line = f.readline()
                    if line:
                        self._emit(line.rstrip("\n"))
                        continue
                    if self._stop_flag.is_set() or self.stop_when():
                        tail = f.read()
                        if tail:
                            for ln in tail.splitlines():
                                self._emit(ln)
                        return
                    time.sleep(self.poll_interval)
        except Exception:
            logger.warning("Run log tailer crashed for %s", self.handle.run_id, exc_info=True)

    def _emit(self, line: str) -> None:
        self.handle.push_event({"event": "log", "message": line})

    def stop_and_join(self, timeout: float = 2.0) -> None:
        self._stop_flag.set()
        self.join(timeout=timeout)


class _RunReattachedMonitor:
    """Watches a reattached pipeline PID and tails its log file."""

    def __init__(
        self,
        handle: RunHandle,
        manager: "RunManager",
        state: RunStateFile,
    ):
        self.handle = handle
        self.manager = manager
        self.state = state

    def run(self) -> None:
        log_path = Path(self.handle.log_path) if self.handle.log_path else None
        proc_dead = threading.Event()

        def stop_when() -> bool:
            if not RunRegistry.pid_alive(self.handle.pid):
                proc_dead.set()
                return True
            return False

        tailer = None
        if log_path and log_path.is_file():
            tailer = _RunLogTailer(log_path, self.handle, stop_when=stop_when)
            tailer.start()

        while RunRegistry.pid_alive(self.handle.pid):
            time.sleep(1.0)
        proc_dead.set()

        if tailer is not None:
            tailer.stop_and_join()

        self._finalize()

    def _finalize(self) -> None:
        summary_path = (
            Path(self.handle.output_dir) / 'run_summary.json'
            if self.handle.output_dir else None
        )
        now = time.time()
        if summary_path and summary_path.is_file():
            self.handle.status = 'done'
            self.handle.finished_at = now
            self.handle.push_event({
                'event': 'run_done',
                'summary_path': str(summary_path),
                'elapsed': now - self.handle.started_at,
            })
        else:
            self.handle.status = 'failed'
            self.handle.error = 'subprocess exited without a run_summary.json'
            self.handle.finished_at = now
            self.handle.push_event({
                'event': 'run_failed',
                'error': self.handle.error,
                'elapsed': now - self.handle.started_at,
            })
        self.manager._persist_state(self.handle)


def _read_tail(path: str | None, n: int = 200) -> str:
    if not path:
        return ""
    try:
        p = Path(path)
        if not p.is_file():
            return ""
        lines = p.read_text(errors="replace").splitlines()
        return "\n".join(lines[-n:])
    except Exception:
        return ""


# Known pipeline stages, in pipeline execution order.
_ANALYSIS_STAGES = (
    'stimuli', 'responses', 'features',
    'prepare', 'model', 'analyze', 'report',
)


def _parse_events_file(path: str | None) -> list[dict]:
    """Parse the pipeline subprocess's events.jsonl into a stage list.

    Each line is one JSON event:
      - stage_start {stage, t}
      - stage_done  {stage, t, elapsed, detail}
      - stage_fail  {stage, t, elapsed, error}
      - stage_warn  {stage, t, elapsed, detail}

    Returns the stages in the order they first appeared, each with
    its current status ('running' / 'ok' / 'warning' / 'failed'),
    started_at, finished_at, elapsed, detail, and error fields.
    Returns [] when there's no events file yet (e.g. subprocess
    just started, or this isn't an analysis run).
    """
    if not path:
        return []
    p = Path(path)
    if not p.is_file():
        return []

    # Preserve insertion order via dict + list to handle the unusual
    # case where a stage appears twice (e.g. resume).
    order: list[str] = []
    by_name: dict[str, dict] = {}

    try:
        raw = p.read_text(errors='replace')
    except Exception:
        return []

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except Exception:
            continue
        event = ev.get('event')
        stage = ev.get('stage')
        if not stage or event not in (
            'stage_start', 'stage_done', 'stage_fail', 'stage_warn',
        ):
            continue

        if stage not in by_name:
            by_name[stage] = {
                'stage': stage,
                'status': 'pending',
                'started_at': 0.0,
                'finished_at': 0.0,
                'elapsed': 0.0,
                'detail': '',
                'error': None,
            }
            order.append(stage)

        slot = by_name[stage]
        t = ev.get('t', 0.0)
        if event == 'stage_start':
            slot['status'] = 'running'
            slot['started_at'] = t
        elif event == 'stage_done':
            slot['status'] = 'ok'
            slot['finished_at'] = t
            slot['elapsed'] = ev.get('elapsed', 0.0)
            slot['detail'] = ev.get('detail', '')
        elif event == 'stage_warn':
            slot['status'] = 'warning'
            slot['finished_at'] = t
            slot['elapsed'] = ev.get('elapsed', 0.0)
            slot['detail'] = ev.get('detail', '')
        elif event == 'stage_fail':
            slot['status'] = 'failed'
            slot['finished_at'] = t
            slot['elapsed'] = ev.get('elapsed', 0.0)
            slot['error'] = ev.get('error', '')

    return [by_name[s] for s in order]
