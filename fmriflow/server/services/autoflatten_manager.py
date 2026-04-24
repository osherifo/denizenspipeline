"""Autoflatten manager — background execution with log streaming.

Runs that actually spawn the autoflatten CLI are detached from the server
(``start_new_session=True``) with stdout+stderr written to
``~/.fmriflow/runs/{run_id}/stdout.log`` and a ``state.json`` sidecar, so
hour-long flattening jobs survive server restarts. On startup we scan
the registry and reattach any live PIDs.

Import-only / pre-computed runs stay in-process (they're fast) — they
get registered in the run log but never go through the detach path.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess as _subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from fmriflow.server.services.run_registry import RunRegistry, RunStateFile

logger = logging.getLogger(__name__)


@dataclass
class AutoflattenRunHandle:
    """Tracks a running or reattached autoflatten job."""
    run_id: str
    subject: str
    status: str = "running"   # running, done, failed, cancelled, lost
    events: list[dict] = field(default_factory=list)
    _pending: list[dict] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    result: dict | None = None
    error: str | None = None
    started_at: float = 0.0
    finished_at: float = 0.0

    # Detach-reattach bookkeeping
    pid: int | None = None
    pgid: int | None = None
    log_path: str | None = None
    is_reattached: bool = False
    params: dict = field(default_factory=dict)

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
            "subject": self.subject,
            "status": self.status,
            "pid": self.pid,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "is_reattached": self.is_reattached,
            "error": self.error,
            "log_path": self.log_path,
            "result": self.result,
        }


class AutoflattenManager:
    """Manages autoflatten runs with background execution and log streaming."""

    def __init__(self, registry: RunRegistry | None = None) -> None:
        self.active_runs: dict[str, AutoflattenRunHandle] = {}
        self.registry = registry or RunRegistry()
        try:
            self._reattach_active_runs()
        except Exception:
            logger.warning(
                "Failed to scan autoflatten run registry on startup",
                exc_info=True,
            )

    # ── Entry points ────────────────────────────────────────────────

    def start_run_from_config_file(
        self,
        config_path: str,
        overrides: dict | None = None,
    ) -> str:
        """Start an autoflatten run from a YAML file."""
        import yaml as _yaml

        path = Path(config_path)
        if not path.is_file():
            raise FileNotFoundError(f"Autoflatten config not found: {path}")
        with open(path) as f:
            data = _yaml.safe_load(f) or {}
        section = data.get("autoflatten")
        if not isinstance(section, dict):
            raise ValueError(
                f"Config '{path.name}' has no 'autoflatten:' section"
            )
        params: dict = dict(section)
        if overrides:
            params.update({k: v for k, v in overrides.items() if v is not None})
        for field_name in ("subjects_dir", "subject"):
            if not params.get(field_name):
                raise ValueError(
                    f"Autoflatten config missing required field '{field_name}'"
                )
        return self.start_run(params)

    def start_run(self, params: dict) -> str:
        """Start an autoflatten run in a background thread."""
        run_id = f"autoflatten_{params.get('subject', 'unknown')}_{uuid.uuid4().hex[:8]}"
        now = time.time()

        handle = AutoflattenRunHandle(
            run_id=run_id,
            subject=params.get("subject", "unknown"),
            started_at=now,
            params=params,
        )

        state = RunStateFile(
            run_id=run_id,
            kind="autoflatten",
            backend="autoflatten",
            subject=params.get("subject", "unknown"),
            status="running",
            started_at=now,
            params=params,
        )
        self.registry.register(state)
        handle.log_path = state.stdout_log

        self.active_runs[run_id] = handle

        thread = threading.Thread(
            target=self._execute_run,
            args=(handle, params),
            daemon=True,
            name=f"autoflatten-{run_id}",
        )
        thread.start()
        return run_id

    # ── Execution ────────────────────────────────────────────────────

    def _execute_run(self, handle: AutoflattenRunHandle, params: dict) -> None:
        """Dispatch to detached CLI spawn if flattening is needed, else in-process."""
        from fmriflow.preproc.autoflatten import (
            AutoflattenConfig,
            _resolve_flat_patches,
            _resolve_hemispheres,
        )

        try:
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

            hemis = _resolve_hemispheres(config.hemispheres)
            _, source = _resolve_flat_patches(config, hemis)

            if source == "autoflatten":
                self._execute_detached(handle, params, config, hemis)
            else:
                # import_only / precomputed — short and in-process.
                self._execute_inprocess(handle, params, config)
        except Exception as e:
            import traceback as _tb
            tb_text = _tb.format_exc()
            handle.status = "failed"
            handle.error = f"{type(e).__name__}: {e}"
            handle.finished_at = time.time()
            handle.push_event({
                "event": "failed",
                "error": handle.error,
                "traceback": tb_text,
                "elapsed": handle.finished_at - handle.started_at,
            })
            if handle.log_path:
                try:
                    with open(handle.log_path, "a") as _lf:
                        _lf.write("\n\n=== wrapper traceback ===\n")
                        _lf.write(tb_text)
                except Exception:
                    pass
            logger.error("Autoflatten failed: %s", e, exc_info=True)
        finally:
            self._persist_state(handle)

    def _execute_detached(
        self,
        handle: AutoflattenRunHandle,
        params: dict,
        config,
        hemis: list[str],
    ) -> None:
        """Spawn autoflatten CLI detached, tail its log, finalize + pycortex import."""
        from fmriflow.preproc.autoflatten import (
            AutoflattenRecord,
            AutoflattenResult,
            _build_autoflatten_command,
            _do_pycortex_import,
        )

        log_path = Path(handle.log_path) if handle.log_path else None

        cmd = _build_autoflatten_command(config)
        handle.push_event({
            "event": "started",
            "message": f"Starting autoflatten for {config.subject}",
        })

        log_fh = None
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
        finally:
            if log_fh is not None:
                log_fh.close()

        handle.pid = proc.pid
        try:
            handle.pgid = os.getpgid(proc.pid)
        except OSError:
            handle.pgid = proc.pid
        self._persist_state(handle)

        tailer = None
        if log_path is not None:
            tailer = _AutoflattenLogTailer(
                log_path, handle, stop_when=lambda: proc.poll() is not None,
            )
            tailer.start()

        proc.wait()
        if tailer is not None:
            tailer.stop_and_join()

        if proc.returncode != 0:
            raise RuntimeError(f"autoflatten exited with code {proc.returncode}")

        # Collect outputs
        output_dir = Path(config.output_dir) if config.output_dir else (
            Path(config.subjects_dir) / config.subject / "surf"
        )
        flat_patches: dict[str, Path] = {}
        visualizations: dict[str, Path] = {}
        for hemi in hemis:
            patch = output_dir / f"{hemi}.autoflatten.flat.patch.3d"
            if patch.is_file():
                flat_patches[hemi] = patch
            viz = output_dir / f"{hemi}.autoflatten.flat.patch.png"
            if viz.is_file():
                visualizations[hemi] = viz
        if not flat_patches:
            raise RuntimeError(
                f"autoflatten finished but no flat patches in {output_dir}"
            )

        # pycortex import (in-process, quick)
        pycortex_surface = None
        if config.import_to_pycortex and flat_patches:
            pycortex_surface = _do_pycortex_import(config, flat_patches)

        elapsed = time.time() - handle.started_at
        result = AutoflattenResult(
            subject=config.subject,
            hemispheres=list(flat_patches.keys()),
            flat_patches={h: str(p) for h, p in flat_patches.items()},
            visualizations={h: str(p) for h, p in visualizations.items()},
            pycortex_surface=pycortex_surface,
            source="autoflatten",
            elapsed_s=elapsed,
        )
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

    def _execute_inprocess(
        self,
        handle: AutoflattenRunHandle,
        params: dict,
        config,
    ) -> None:
        """Fast path: import-only or precomputed flat patches."""
        from fmriflow.preproc.autoflatten import AutoflattenRecord, run_autoflatten

        capture = _LogCapture(handle)
        af_logger = logging.getLogger("fmriflow.preproc.autoflatten")
        af_logger.addHandler(capture)
        fm_logger = logging.getLogger("fmriflow")
        fm_logger.addHandler(capture)
        try:
            handle.push_event({
                "event": "started",
                "message": f"Starting autoflatten (import/precomputed) for {config.subject}",
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
        finally:
            af_logger.removeHandler(capture)
            fm_logger.removeHandler(capture)

    # ── Registry / reattach / cancel ─────────────────────────────────

    def _persist_state(self, handle: AutoflattenRunHandle) -> None:
        state = RunStateFile(
            run_id=handle.run_id,
            kind="autoflatten",
            backend="autoflatten",
            subject=handle.subject,
            status=handle.status,
            pid=handle.pid,
            pgid=handle.pgid,
            started_at=handle.started_at,
            finished_at=handle.finished_at,
            stdout_log=handle.log_path or "",
            params=handle.params,
            error=handle.error,
        )
        self.registry.update(state)

    def _reattach_active_runs(self) -> None:
        for state in self.registry.list_active():
            if state.kind != "autoflatten":
                continue
            if not RunRegistry.pid_alive(state.pid):
                self.registry.mark_lost(state, "server_lost_track")
                continue

            handle = AutoflattenRunHandle(
                run_id=state.run_id,
                subject=state.subject,
                status="running",
                started_at=state.started_at,
                pid=state.pid,
                pgid=state.pgid,
                log_path=state.stdout_log,
                is_reattached=True,
                params=state.params,
            )
            self.active_runs[state.run_id] = handle

            monitor = _AutoflattenReattachedMonitor(handle, self, state)
            thread = threading.Thread(
                target=monitor.run, daemon=True,
                name=f"reattach-autoflatten-{state.run_id}",
            )
            thread.start()
            logger.info(
                "Reattached to autoflatten run %s (pid=%s, subject=%s)",
                state.run_id, state.pid, state.subject,
            )

    def list_runs(self, include_finished: bool = True) -> list[dict]:
        out: dict[str, dict] = {}
        for handle in self.active_runs.values():
            out[handle.run_id] = handle.to_summary()
        if include_finished:
            for state in self.registry.list_all():
                if state.kind != "autoflatten" or state.run_id in out:
                    continue
                out[state.run_id] = {
                    "run_id": state.run_id,
                    "subject": state.subject,
                    "status": state.status,
                    "pid": state.pid,
                    "started_at": state.started_at,
                    "finished_at": state.finished_at,
                    "is_reattached": False,
                    "error": state.error,
                    "log_path": state.stdout_log,
                    "result": None,
                }
        return sorted(out.values(), key=lambda r: r.get("started_at") or 0, reverse=True)

    def get_run(self, run_id: str) -> dict | None:
        handle = self.active_runs.get(run_id)
        if handle is not None:
            summary = handle.to_summary()
        else:
            state = self.registry.load(run_id)
            if state is None or state.kind != "autoflatten":
                return None
            summary = {
                "run_id": state.run_id,
                "subject": state.subject,
                "status": state.status,
                "pid": state.pid,
                "started_at": state.started_at,
                "finished_at": state.finished_at,
                "is_reattached": False,
                "error": state.error,
                "log_path": state.stdout_log,
                "result": None,
            }
        # Preserve existing run-detail shape: include an events list so the
        # existing Autoflatten polling code keeps working, even though the
        # new clients prefer WebSocket + log_tail.
        if handle is not None:
            summary["events"] = list(handle.events)
        else:
            summary["events"] = []
        log_path = summary.get("log_path")
        summary["log_tail"] = _read_tail(log_path, n=200) if log_path else ""
        return summary

    def cancel_run(self, run_id: str) -> dict:
        handle = self.active_runs.get(run_id)
        if handle is None:
            return {"cancelled": False, "reason": "run not found in active set"}
        if handle.status != "running":
            return {"cancelled": False, "reason": f"status is {handle.status}"}
        pgid = handle.pgid or handle.pid
        if not pgid:
            return {"cancelled": False, "reason": "no pid recorded (in-process run)"}
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            handle.status = "failed"
            handle.error = "process already gone"
            self._persist_state(handle)
            return {"cancelled": True, "reason": "process already exited"}
        except Exception as e:
            return {"cancelled": False, "reason": str(e)}

        def _grace_kill():
            time.sleep(5)
            if RunRegistry.pid_alive(handle.pid):
                try:
                    os.killpg(pgid, signal.SIGKILL)
                except Exception:
                    pass
        threading.Thread(target=_grace_kill, daemon=True).start()

        handle.status = "cancelled"
        handle.finished_at = time.time()
        handle.push_event({"event": "cancelled", "message": "SIGTERM sent"})
        self._persist_state(handle)
        return {"cancelled": True}


# ── Helpers ─────────────────────────────────────────────────────────────


class _LogCapture(logging.Handler):
    """Logging handler used only for the fast in-process path."""

    def __init__(self, run_handle: AutoflattenRunHandle):
        super().__init__()
        self.run_handle = run_handle
        self.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
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


class _AutoflattenLogTailer(threading.Thread):
    """Tails the autoflatten CLI log file into the handle's event stream."""

    def __init__(
        self,
        log_path: Path,
        handle: AutoflattenRunHandle,
        stop_when,
        poll_interval: float = 0.5,
    ):
        super().__init__(daemon=True, name=f"autoflatten-tail-{handle.run_id}")
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
            logger.warning("Autoflatten log tailer crashed for %s", self.handle.run_id, exc_info=True)

    def _emit(self, line: str) -> None:
        self.handle.push_event({"event": "log", "message": line})

    def stop_and_join(self, timeout: float = 2.0) -> None:
        self._stop_flag.set()
        self.join(timeout=timeout)


class _AutoflattenReattachedMonitor:
    """Watches a reattached autoflatten PID + tails its log file."""

    def __init__(
        self,
        handle: AutoflattenRunHandle,
        manager: "AutoflattenManager",
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
            tailer = _AutoflattenLogTailer(log_path, self.handle, stop_when=stop_when)
            tailer.start()

        while RunRegistry.pid_alive(self.handle.pid):
            time.sleep(1.0)
        proc_dead.set()

        if tailer is not None:
            tailer.stop_and_join()

        self._finalize()

    def _finalize(self) -> None:
        params = self.state.params or {}
        subjects_dir = params.get("subjects_dir")
        subject = self.state.subject
        hemispheres = params.get("hemispheres", "both")
        output_dir = params.get("output_dir")
        hemis = ["lh", "rh"] if hemispheres == "both" else [hemispheres]

        target_dir = (
            Path(output_dir) if output_dir
            else Path(subjects_dir) / subject / "surf"
            if subjects_dir else None
        )
        found = {}
        if target_dir and target_dir.is_dir():
            for h in hemis:
                patch = target_dir / f"{h}.autoflatten.flat.patch.3d"
                if patch.is_file():
                    found[h] = str(patch)

        now = time.time()
        if found and len(found) == len(hemis):
            self.handle.status = "done"
            self.handle.finished_at = now
            self.handle.push_event({
                "event": "done",
                "message": "flat patches found after reattach",
                "elapsed": now - self.handle.started_at,
            })
        else:
            self.handle.status = "failed"
            self.handle.error = (
                f"subprocess exited without producing all expected flat patches "
                f"(found {list(found.keys())}, expected {hemis})"
            )
            self.handle.finished_at = now
            self.handle.push_event({
                "event": "failed",
                "error": self.handle.error,
                "elapsed": now - self.handle.started_at,
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
