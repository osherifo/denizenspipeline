"""Preprocessing manager — manifest scanning, collect, and run orchestration.

Runs survive server restarts: each job is spawned in its own process group
(``start_new_session=True``) with stdout+stderr redirected to a log file,
and a ``RunStateFile`` is persisted under ``~/.fmriflow/runs/{run_id}/``.
On startup we scan that directory and reattach to any runs whose PID is
still alive; their progress is rebuilt by tailing the log file.
"""

from __future__ import annotations

import logging
import os
import signal
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from fmriflow.server.services.run_registry import (
    RunRegistry,
    RunStateFile,
)

logger = logging.getLogger(__name__)


# ── Handle ───────────────────────────────────────────────────────────────


@dataclass
class PreprocRunHandle:
    """Tracks a running or reattached preprocessing job.

    Two flavours:

    - **Native**: this server spawned the subprocess. ``proc`` is the
      ``Popen``; events come from the log-file tailer thread.
    - **Reattached**: a previous server spawned it; the subprocess is
      still alive (``pid`` resolves). Events come from the tailer
      reading the existing log file; completion is inferred by polling
      ``pid`` and checking for the fmriprep HTML report.
    """

    run_id: str
    subject: str
    backend: str
    status: str = "running"   # running, done, failed, cancelled, lost
    events: list[dict] = field(default_factory=list)
    _pending: list[dict] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    manifest_path: str | None = None
    error: str | None = None
    started_at: float = 0.0
    finished_at: float = 0.0

    # Detach-reattach bookkeeping
    pid: int | None = None
    pgid: int | None = None
    log_path: str | None = None
    is_reattached: bool = False
    config_path: str | None = None
    params: dict = field(default_factory=dict)
    # JSONL of parsed nipype-node events, populated by _LogTailer when the
    # backend is fmriprep. Used by /api/preproc/runs/{run_id}/live.
    nipype_jsonl_path: str | None = None

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
            "backend": self.backend,
            "status": self.status,
            "pid": self.pid,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "is_reattached": self.is_reattached,
            "manifest_path": self.manifest_path,
            "error": self.error,
            "config_path": self.config_path,
            "log_path": self.log_path,
            "nipype_jsonl_path": self.nipype_jsonl_path,
        }


# ── Manager ──────────────────────────────────────────────────────────────


class PreprocManager:
    """Manages manifest discovery and preprocessing runs."""

    def __init__(
        self,
        derivatives_dir: Path,
        registry: RunRegistry | None = None,
    ):
        self.derivatives_dir = derivatives_dir
        self._manifests_cache: list[dict] | None = None
        self._cache_time: float = 0
        self._cache_ttl = 10.0
        self.active_runs: dict[str, PreprocRunHandle] = {}
        self.registry = registry or RunRegistry()

        # Best-effort reattach on startup.
        try:
            self._reattach_active_runs()
        except Exception:
            logger.warning("Failed to scan run registry on startup", exc_info=True)

    # ── Manifest scanning ────────────────────────────────────────

    def scan_manifests(self) -> list[dict]:
        """Scan derivatives dir for preproc_manifest.json files."""
        now = time.time()
        if self._manifests_cache is not None and (now - self._cache_time) < self._cache_ttl:
            return self._manifests_cache

        manifests = []
        if not self.derivatives_dir.is_dir():
            self._manifests_cache = []
            self._cache_time = now
            return []

        for mf in sorted(self.derivatives_dir.rglob("preproc_manifest.json")):
            try:
                from fmriflow.preproc.manifest import PreprocManifest
                m = PreprocManifest.from_json(mf)
                manifests.append({
                    "subject": m.subject,
                    "path": str(mf),
                    "backend": m.backend,
                    "backend_version": m.backend_version,
                    "space": m.space,
                    "n_runs": len(m.runs),
                    "created": m.created,
                    "dataset": m.dataset,
                })
            except Exception:
                logger.warning("Could not read manifest: %s", mf, exc_info=True)

        self._manifests_cache = manifests
        self._cache_time = now
        return manifests

    def invalidate_cache(self) -> None:
        self._manifests_cache = None

    def get_manifest(self, subject: str) -> dict | None:
        """Get full manifest dict for a subject."""
        manifests = self.scan_manifests()
        for m in manifests:
            if m["subject"] == subject:
                try:
                    from fmriflow.preproc.manifest import PreprocManifest
                    manifest = PreprocManifest.from_json(m["path"])
                    return manifest.to_dict()
                except Exception:
                    return None
        return None

    def validate_manifest(self, subject: str, config_filename: str | None = None) -> dict:
        """Validate a manifest, optionally against an analysis config."""
        manifests = self.scan_manifests()
        path = None
        for m in manifests:
            if m["subject"] == subject:
                path = m["path"]
                break
        if path is None:
            return {"errors": [f"No manifest found for subject '{subject}'"]}

        from fmriflow.preproc.manifest import PreprocManifest
        from fmriflow.preproc.validation import validate_manifest

        manifest = PreprocManifest.from_json(path)
        config = None
        if config_filename:
            try:
                from fmriflow.config.loader import load_config
                config = load_config(config_filename)
            except Exception as e:
                return {"errors": [f"Cannot load config: {e}"]}

        errors = validate_manifest(manifest, config)
        return {"errors": errors}

    # ── Collect ──────────────────────────────────────────────────

    def collect(self, params: dict) -> dict:
        """Collect outputs into a manifest."""
        from fmriflow.preproc.manifest import PreprocConfig
        from fmriflow.preproc.runner import collect_outputs

        config = PreprocConfig(
            subject=params["subject"],
            backend=params["backend"],
            output_dir=params["output_dir"],
            bids_dir=params.get("bids_dir"),
            task=params.get("task"),
            sessions=params.get("sessions"),
            run_map=params.get("run_map"),
            backend_params=params.get("backend_params", {}),
        )

        manifest = collect_outputs(config)
        self.invalidate_cache()

        return {
            "manifest": manifest.to_dict(),
            "manifest_path": str(
                Path(config.output_dir) / f"sub-{config.subject}" / "preproc_manifest.json"
            ),
        }

    # ── Run preprocessing ────────────────────────────────────────

    def start_run(self, params: dict, config_path: str | None = None) -> str:
        """Start a preprocessing run in a background thread."""
        run_id = f"preproc_{params['subject']}_{uuid.uuid4().hex[:8]}"
        now = time.time()

        handle = PreprocRunHandle(
            run_id=run_id,
            subject=params["subject"],
            backend=params["backend"],
            started_at=now,
            config_path=config_path,
            params=params,
        )

        # Pre-register so that even if spawn fails, there's a record on disk.
        state = RunStateFile(
            run_id=run_id,
            kind="preproc",
            backend=params["backend"],
            subject=params["subject"],
            status="running",
            started_at=now,
            config_path=config_path,
            params=params,
        )
        self.registry.register(state)
        handle.log_path = state.stdout_log
        # Sibling JSONL for parsed nipype-node events (only fmriprep populates it).
        if params.get("backend") == "fmriprep":
            handle.nipype_jsonl_path = str(
                Path(state.stdout_log).parent / "nipype_events.jsonl"
            )

        self.active_runs[run_id] = handle

        thread = threading.Thread(
            target=self._execute_run,
            args=(handle, params),
            daemon=True,
            name=f"preproc-{run_id}",
        )
        thread.start()
        return run_id

    def start_run_from_config_file(
        self,
        config_path: str,
        overrides: dict | None = None,
    ) -> str:
        """Start a preprocessing run from a YAML config file.

        The file must contain a top-level ``preproc:`` section matching the
        :class:`fmriflow.preproc.manifest.PreprocConfig` schema. Optional
        ``overrides`` is shallow-merged on top of the section before running.
        """
        import yaml as _yaml

        path = Path(config_path)
        if not path.is_file():
            raise FileNotFoundError(f"Preproc config not found: {path}")

        with open(path) as f:
            data = _yaml.safe_load(f) or {}
        section = data.get("preproc")
        if not isinstance(section, dict):
            raise ValueError(
                f"Config '{path.name}' has no 'preproc:' section"
            )

        params: dict = dict(section)
        if overrides:
            params.update({k: v for k, v in overrides.items() if v is not None})

        missing = [k for k in ("subject", "backend", "output_dir") if not params.get(k)]
        if missing:
            raise ValueError(
                f"Preproc config missing required fields: {', '.join(missing)}"
            )

        return self.start_run(params, config_path=str(path.resolve()))

    def _execute_run(self, handle: PreprocRunHandle, params: dict) -> None:
        """Dispatch to the right execution strategy based on backend."""
        if params.get("backend") == "fmriprep":
            self._execute_fmriprep(handle, params)
        else:
            self._execute_inprocess(handle, params)

    # ── fmriprep: detached subprocess + log tailer ──────────────────

    def _execute_fmriprep(self, handle: PreprocRunHandle, params: dict) -> None:
        """Spawn fmriprep detached, tail its log file, update state."""
        from fmriflow.preproc.backends import get_backend
        from fmriflow.preproc.manifest import PreprocConfig, ConfoundsConfig
        from fmriflow.preproc.errors import BackendRunError

        log_path = Path(handle.log_path) if handle.log_path else None

        try:
            confounds_data = params.get("confounds")
            confounds = ConfoundsConfig(**confounds_data) if confounds_data else None

            config = PreprocConfig(
                subject=params["subject"],
                backend=params["backend"],
                output_dir=params["output_dir"],
                bids_dir=params.get("bids_dir"),
                raw_dir=params.get("raw_dir"),
                work_dir=params.get("work_dir"),
                task=params.get("task"),
                sessions=params.get("sessions"),
                run_map=params.get("run_map"),
                backend_params=params.get("backend_params", {}),
                confounds=confounds,
            )

            backend = get_backend("fmriprep")

            handle.push_event({
                "event": "started",
                "message": f"Starting fmriprep for sub-{config.subject}",
            })

            proc = backend.spawn(config, log_path=log_path)
            handle.pid = proc.pid
            try:
                handle.pgid = os.getpgid(proc.pid)
            except OSError:
                handle.pgid = proc.pid
            self._persist_state(handle)

            def _sigterm_proc_group():
                pgid = handle.pgid or handle.pid
                if not pgid:
                    return
                try:
                    os.killpg(pgid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                except Exception:
                    logger.warning(
                        "Failed to SIGTERM pgid=%s on fatal log line", pgid,
                        exc_info=True,
                    )

            nipype_jsonl_path = (
                Path(handle.nipype_jsonl_path) if handle.nipype_jsonl_path else None
            )
            tailer = _LogTailer(
                log_path, handle,
                stop_when=lambda: proc.poll() is not None,
                on_fatal_line=_sigterm_proc_group,
                nipype_jsonl_path=nipype_jsonl_path,
            )
            tailer.start()

            proc.wait()
            tailer.stop_and_join()

            if proc.returncode != 0:
                raise BackendRunError(
                    f"fmriprep exited with code {proc.returncode}",
                    backend="fmriprep",
                    subject=config.subject,
                    returncode=proc.returncode,
                )

            # Build manifest from outputs.
            from fmriflow.preproc.runner import run_preprocessing as _unused  # noqa: F401
            manifest = backend.collect(config)
            if config.confounds:
                from fmriflow.preproc.runner import _apply_confounds
                manifest = _apply_confounds(manifest, config.confounds)

            manifest_path = Path(config.output_dir) / f"sub-{config.subject}" / "preproc_manifest.json"
            manifest.save(manifest_path)

            handle.manifest_path = str(manifest_path)
            handle.status = "done"
            handle.finished_at = time.time()
            handle.push_event({
                "event": "done",
                "manifest_path": handle.manifest_path,
                "n_runs": len(manifest.runs),
                "elapsed": handle.finished_at - handle.started_at,
            })
            self.invalidate_cache()

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
            logger.error("Preprocessing failed: %s", e, exc_info=True)

        finally:
            self._persist_state(handle)

    # ── Non-fmriprep: in-process (custom, bids_app) ─────────────────

    def _execute_inprocess(self, handle: PreprocRunHandle, params: dict) -> None:
        """Legacy synchronous execution for backends that don't support detach.

        No detach — the subprocess is tied to the server's lifetime. Use
        fmriprep for hands-off long runs until these backends are migrated.
        """
        import logging as _logging
        capture = _LogCapture(handle)
        preproc_logger = _logging.getLogger("fmriflow.preproc")
        preproc_logger.addHandler(capture)

        try:
            from fmriflow.preproc.manifest import PreprocConfig, ConfoundsConfig
            from fmriflow.preproc.runner import run_preprocessing

            confounds_data = params.get("confounds")
            confounds = ConfoundsConfig(**confounds_data) if confounds_data else None

            config = PreprocConfig(
                subject=params["subject"],
                backend=params["backend"],
                output_dir=params["output_dir"],
                bids_dir=params.get("bids_dir"),
                raw_dir=params.get("raw_dir"),
                work_dir=params.get("work_dir"),
                task=params.get("task"),
                sessions=params.get("sessions"),
                run_map=params.get("run_map"),
                backend_params=params.get("backend_params", {}),
                confounds=confounds,
            )

            handle.push_event({
                "event": "started",
                "message": f"Starting {config.backend} for sub-{config.subject}",
            })

            manifest = run_preprocessing(config)

            handle.manifest_path = str(
                Path(config.output_dir) / f"sub-{config.subject}" / "preproc_manifest.json"
            )
            handle.status = "done"
            handle.finished_at = time.time()
            handle.push_event({
                "event": "done",
                "manifest_path": handle.manifest_path,
                "n_runs": len(manifest.runs),
                "elapsed": handle.finished_at - handle.started_at,
            })
            self.invalidate_cache()

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
            logger.error("Preprocessing failed: %s", e, exc_info=True)

        finally:
            preproc_logger.removeHandler(capture)
            self._persist_state(handle)

    # ── Detached run discovery ──────────────────────────────────────

    def _reattach_active_runs(self) -> None:
        """On startup, scan the registry and rehydrate handles for live runs."""
        for state in self.registry.list_active():
            if state.kind != "preproc":
                continue
            if not RunRegistry.pid_alive(state.pid):
                # The subprocess died while the server was down. Record the
                # transition so the history view shows "lost" instead of
                # an eternal "running".
                self.registry.mark_lost(state, "server_lost_track")
                continue

            handle = PreprocRunHandle(
                run_id=state.run_id,
                subject=state.subject,
                backend=state.backend,
                status="running",
                started_at=state.started_at,
                pid=state.pid,
                pgid=state.pgid,
                log_path=state.stdout_log,
                is_reattached=True,
                config_path=state.config_path,
                params=state.params,
            )
            if state.backend == "fmriprep" and state.stdout_log:
                handle.nipype_jsonl_path = str(
                    Path(state.stdout_log).parent / "nipype_events.jsonl"
                )
            self.active_runs[state.run_id] = handle

            monitor = _ReattachedMonitor(handle, self, state)
            thread = threading.Thread(
                target=monitor.run, daemon=True, name=f"reattach-{state.run_id}",
            )
            thread.start()
            logger.info(
                "Reattached to preproc run %s (pid=%s, subject=%s)",
                state.run_id, state.pid, state.subject,
            )

    # ── Run listing / cancel ────────────────────────────────────────

    def list_runs(self, include_finished: bool = True) -> list[dict]:
        """Return in-memory active runs plus (optionally) recent finished ones."""
        out: dict[str, dict] = {}
        for handle in self.active_runs.values():
            out[handle.run_id] = handle.to_summary()
        if include_finished:
            for state in self.registry.list_all():
                if state.kind != "preproc" or state.run_id in out:
                    continue
                out[state.run_id] = {
                    "run_id": state.run_id,
                    "subject": state.subject,
                    "backend": state.backend,
                    "status": state.status,
                    "pid": state.pid,
                    "started_at": state.started_at,
                    "finished_at": state.finished_at,
                    "is_reattached": False,
                    "manifest_path": state.manifest_path,
                    "error": state.error,
                    "config_path": state.config_path,
                    "log_path": state.stdout_log,
                }
        # Newest first
        return sorted(out.values(), key=lambda r: r.get("started_at") or 0, reverse=True)

    def get_run(self, run_id: str) -> dict | None:
        """Return summary + recent log tail for a run (live or historical)."""
        handle = self.active_runs.get(run_id)
        if handle is not None:
            summary = handle.to_summary()
        else:
            state = self.registry.load(run_id)
            if state is None:
                return None
            summary = {
                "run_id": state.run_id,
                "subject": state.subject,
                "backend": state.backend,
                "status": state.status,
                "pid": state.pid,
                "started_at": state.started_at,
                "finished_at": state.finished_at,
                "is_reattached": False,
                "manifest_path": state.manifest_path,
                "error": state.error,
                "config_path": state.config_path,
                "log_path": state.stdout_log,
            }
        log_path = summary.get("log_path")
        summary["log_tail"] = _read_tail(log_path, n=200) if log_path else ""
        return summary

    def delete_run(self, run_id: str) -> dict:
        """Delete a finished preproc run.

        Refuses while the run is still ``running`` — the caller must
        cancel first. Removes the registry dir
        (``~/.fmriflow/runs/<id>/``) and the run's per-subject output
        directory under ``output_dir/sub-<subject>/``. Does not touch
        sibling subjects in the same derivatives tree.

        Returns ``{deleted: bool, reason?: str, removed_paths: [..]}``.
        """
        import shutil

        # Determine current status — prefer in-memory handle, fall
        # back to registry state.
        handle = self.active_runs.get(run_id)
        status = handle.status if handle else None
        state = self.registry.load(run_id)
        if status is None and state is not None:
            status = state.status
        if status == "running":
            return {"deleted": False, "reason": "run is still running; cancel first"}
        if state is None and handle is None:
            return {"deleted": False, "reason": "run not found"}

        # Gather per-subject paths to remove before we nuke state.
        removed: list[str] = []
        subject = (state.subject if state else handle.subject) or ""
        params = (state.params if state else (handle.params if handle else {})) or {}
        output_dir = params.get("output_dir")
        if subject and output_dir:
            sub_out = Path(output_dir) / f"sub-{subject}"
            if sub_out.is_dir():
                try:
                    shutil.rmtree(sub_out)
                    removed.append(str(sub_out))
                except OSError as e:
                    logger.warning("Could not remove %s: %s", sub_out, e)
        # Sibling HTML report (fmriprep writes sub-{subject}.html at
        # the output_dir root).
        if subject and output_dir:
            html = Path(output_dir) / f"sub-{subject}.html"
            if html.is_file():
                try:
                    html.unlink()
                    removed.append(str(html))
                except OSError:
                    pass

        # Drop the handle from the in-memory registry.
        self.active_runs.pop(run_id, None)

        # Finally, remove the ~/.fmriflow/runs/<id>/ dir.
        existed = self.registry.delete(run_id)
        if not existed and not removed:
            return {"deleted": False, "reason": "nothing to delete"}

        self.invalidate_cache()
        return {"deleted": True, "removed_paths": removed}

    def cancel_run(self, run_id: str) -> dict:
        """Terminate a running preproc subprocess. SIGTERM then SIGKILL."""
        handle = self.active_runs.get(run_id)
        if handle is None:
            return {"cancelled": False, "reason": "run not found in active set"}
        if handle.status != "running":
            return {"cancelled": False, "reason": f"status is {handle.status}"}
        pgid = handle.pgid or handle.pid
        if not pgid:
            return {"cancelled": False, "reason": "no pid recorded"}

        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            handle.status = "failed"
            handle.error = "process already gone"
            self._persist_state(handle)
            return {"cancelled": True, "reason": "process already exited"}
        except Exception as e:
            return {"cancelled": False, "reason": str(e)}

        # Give it a short grace period, then hard kill.
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

    # ── Backend availability ─────────────────────────────────────

    def check_backends(self) -> list[dict]:
        """Check availability of all registered backends."""
        from fmriflow.preproc.backends import list_backends, get_backend
        from fmriflow.preproc.manifest import PreprocConfig

        results = []
        for name in list_backends():
            if name == "custom":
                results.append({
                    "name": name,
                    "available": True,
                    "detail": "always available",
                })
                continue

            backend = get_backend(name)
            try:
                cfg = PreprocConfig(
                    subject="test", backend=name, output_dir="/tmp",
                    backend_params={},
                )
                errors = backend.validate(cfg)
                tool_errors = [
                    e for e in errors
                    if "not found" in e.lower() or "not installed" in e.lower()
                ]
                if tool_errors:
                    results.append({
                        "name": name,
                        "available": False,
                        "detail": tool_errors[0],
                    })
                else:
                    results.append({
                        "name": name,
                        "available": True,
                        "detail": "available (config needed)",
                    })
            except Exception as e:
                results.append({
                    "name": name,
                    "available": False,
                    "detail": str(e),
                })

        return results

    # ── Helpers ─────────────────────────────────────────────────────

    def _persist_state(self, handle: PreprocRunHandle) -> None:
        """Flush the handle back to the registry state file.

        On a ``failed`` transition, kick off automatic triage in a
        daemon thread so the UI has KB matches ready by the time the
        user opens the failed run.
        """
        state = RunStateFile(
            run_id=handle.run_id,
            kind="preproc",
            backend=handle.backend,
            subject=handle.subject,
            status=handle.status,
            pid=handle.pid,
            pgid=handle.pgid,
            started_at=handle.started_at,
            finished_at=handle.finished_at,
            stdout_log=handle.log_path or "",
            config_path=handle.config_path,
            params=handle.params,
            error=handle.error,
            manifest_path=handle.manifest_path,
        )
        self.registry.update(state)

        from fmriflow.triage.service import trigger_on_failure
        trigger_on_failure(
            run_id=handle.run_id,
            kind="preproc",
            status=handle.status,
            state=state.to_dict(),
            run_dir=self.registry.run_dir(handle.run_id),
        )


# ── Log tailer ───────────────────────────────────────────────────────────


class _LogTailer(threading.Thread):
    """Reads new lines from a log file and pushes them as events.

    Polls with a short sleep; line-buffered fmriprep output shows up
    within a second. Stops when ``stop_when()`` returns True AND the
    file has no further bytes to read.

    If ``on_fatal_line`` is provided, it is invoked the first time a
    terminal fmriprep failure marker appears in the log (nipype's
    `CRITICAL: fMRIPrep failed` line). fmriprep's multiproc plugin
    otherwise keeps scheduling other nodes for many seconds after a
    node crashes, during which the subprocess is still alive and the
    UI still reads as "running".
    """

    # Regex: nipype's CRITICAL line that precedes fmriprep's terminal
    # traceback. Matched greedily — any line containing all three
    # markers qualifies, which covers the multi-line CRITICAL frame
    # nipype emits on stdout.
    _FATAL_MARKERS = (
        "fMRIPrep failed:",
        "recon-all: version check failed",
    )

    def __init__(
        self,
        log_path: Path,
        handle: PreprocRunHandle,
        stop_when,
        poll_interval: float = 0.5,
        on_fatal_line=None,
        nipype_jsonl_path: Path | None = None,
    ):
        super().__init__(daemon=True, name=f"tail-{handle.run_id}")
        self.log_path = log_path
        self.handle = handle
        self.stop_when = stop_when
        self.poll_interval = poll_interval
        self._stop_flag = threading.Event()
        self._on_fatal_line = on_fatal_line
        self._fatal_fired = False
        # Optional nipype log parsing (only meaningful for fmriprep stdout).
        self._nipype_jsonl_path = nipype_jsonl_path
        if nipype_jsonl_path is not None:
            from fmriflow.preproc.nipype_log import NipypeLogParser
            self._nipype_parser: object | None = NipypeLogParser()
        else:
            self._nipype_parser = None

    def run(self) -> None:
        # Wait briefly for the file to exist
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
                    # No new line — check whether to stop
                    if self._stop_flag.is_set() or self.stop_when():
                        # Drain anything the subprocess wrote between the
                        # last readline and the stop check.
                        tail = f.read()
                        if tail:
                            for ln in tail.splitlines():
                                self._emit(ln)
                        return
                    time.sleep(self.poll_interval)
        except Exception:
            logger.warning("Log tailer crashed for %s", self.handle.run_id, exc_info=True)

    def _emit(self, line: str) -> None:
        self.handle.push_event({"event": "log", "message": line})

        # Parse nipype lines (cheap; one regex check per line) and persist.
        if self._nipype_parser is not None and self._nipype_jsonl_path is not None:
            try:
                from fmriflow.preproc.nipype_log import append_jsonl
                for ev in self._nipype_parser.feed(line):
                    append_jsonl(self._nipype_jsonl_path, ev)
                    # Also push to in-memory event queue for any live consumers.
                    self.handle.push_event(ev)
            except Exception:
                # Never let log parsing kill the tailer.
                logger.debug(
                    "nipype log parser raised", exc_info=True,
                )

        if not self._fatal_fired and self._on_fatal_line is not None:
            for marker in self._FATAL_MARKERS:
                if marker in line:
                    self._fatal_fired = True
                    self.handle.push_event({
                        "event": "fatal_detected",
                        "message": f"Terminal fmriprep error detected in log: {line}",
                    })
                    try:
                        self._on_fatal_line()
                    except Exception:
                        logger.warning(
                            "Fatal-line callback raised for %s",
                            self.handle.run_id, exc_info=True,
                        )
                    break

    def stop_and_join(self, timeout: float = 2.0) -> None:
        self._stop_flag.set()
        self.join(timeout=timeout)


# ── Reattached-run monitor ───────────────────────────────────────────────


class _ReattachedMonitor:
    """Tails the log file of a reattached run and watches its PID.

    When the PID dies, infer outcome:
      * if a fmriprep HTML report exists in the output dir → ``done``
      * otherwise → ``failed``
    """

    def __init__(
        self,
        handle: PreprocRunHandle,
        manager: "PreprocManager",
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

        def _sigterm_proc_group():
            pgid = self.handle.pgid or self.handle.pid
            if not pgid:
                return
            try:
                os.killpg(pgid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            except Exception:
                logger.warning(
                    "Failed to SIGTERM pgid=%s on fatal log line", pgid,
                    exc_info=True,
                )

        tailer = None
        if log_path and log_path.is_file():
            nipype_jsonl_path = (
                Path(self.handle.nipype_jsonl_path)
                if self.handle.nipype_jsonl_path else None
            )
            tailer = _LogTailer(
                log_path, self.handle,
                stop_when=stop_when,
                on_fatal_line=_sigterm_proc_group,
                nipype_jsonl_path=nipype_jsonl_path,
            )
            tailer.start()

        # Poll PID until it dies
        while RunRegistry.pid_alive(self.handle.pid):
            time.sleep(1.0)
        proc_dead.set()

        if tailer is not None:
            tailer.stop_and_join()

        # Infer outcome from output dir
        self._finalize()

    def _finalize(self) -> None:
        """Determine the final status of a reattached run."""
        params = self.state.params or {}
        output_dir = params.get("output_dir")
        subject = self.state.subject
        found_report = False
        if output_dir and subject:
            p = Path(output_dir)
            if p.is_dir():
                reports = list(p.glob(f"sub-{subject}*.html"))
                found_report = bool(reports)

        now = time.time()
        if found_report:
            self.handle.status = "done"
            self.handle.finished_at = now
            self.handle.manifest_path = str(
                Path(output_dir) / f"sub-{subject}" / "preproc_manifest.json"
            ) if output_dir else None
            self.handle.push_event({
                "event": "done",
                "message": "fmriprep report found after reattach",
                "manifest_path": self.handle.manifest_path,
                "elapsed": now - self.handle.started_at,
            })
            # Best-effort rebuild the manifest for the dashboard.
            try:
                from fmriflow.preproc.backends import get_backend
                from fmriflow.preproc.manifest import PreprocConfig
                cfg = PreprocConfig(
                    subject=subject,
                    backend=self.state.backend,
                    output_dir=output_dir,
                    bids_dir=params.get("bids_dir"),
                    task=params.get("task"),
                    sessions=params.get("sessions"),
                    run_map=params.get("run_map"),
                    backend_params=params.get("backend_params", {}),
                )
                manifest = get_backend(self.state.backend).collect(cfg)
                manifest.save(Path(self.handle.manifest_path))
            except Exception:
                logger.warning(
                    "Could not rebuild manifest for reattached run %s",
                    self.handle.run_id, exc_info=True,
                )
        else:
            self.handle.status = "failed"
            self.handle.error = "process exited without producing a fmriprep report"
            self.handle.finished_at = now
            self.handle.push_event({
                "event": "failed",
                "error": self.handle.error,
                "elapsed": now - self.handle.started_at,
            })

        self.manager._persist_state(self.handle)
        self.manager.invalidate_cache()


# ── Helpers ──────────────────────────────────────────────────────────────


def _read_tail(path: str | None, n: int = 200) -> str:
    """Return the last *n* lines of a file, or empty string on failure."""
    if not path:
        return ""
    try:
        p = Path(path)
        if not p.is_file():
            return ""
        # Cheap implementation — big fmriprep logs fit in RAM fine.
        lines = p.read_text(errors="replace").splitlines()
        return "\n".join(lines[-n:])
    except Exception:
        return ""


# ── Legacy log-capture handler (still used by in-process backends) ──────


class _LogCapture(logging.Handler):
    """Logging handler that pushes log records as events to a run handle."""

    def __init__(self, run_handle: PreprocRunHandle):
        super().__init__()
        self.run_handle = run_handle

    def emit(self, record: logging.LogRecord) -> None:
        self.run_handle.push_event({
            "event": "log",
            "message": self.format(record),
        })
