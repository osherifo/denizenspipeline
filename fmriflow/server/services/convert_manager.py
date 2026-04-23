"""Conversion manager — heuristic listing, manifest scanning, and run orchestration.

Single-subject heudiconv runs are detached from the server process
(``start_new_session=True``) with stdout+stderr redirected to a log file
under ``~/.fmriflow/runs/{run_id}/stdout.log``, and a ``RunStateFile`` is
persisted alongside. On startup the manager scans the registry and
reattaches any live heudiconv subprocesses whose PID is still alive.

Batch jobs spawn each heudiconv with the same detach treatment, so the
conversions survive server restarts — but batch grouping is lost on
reattach (individual jobs re-appear as standalone convert runs in the
In-Flight panel).
"""

from __future__ import annotations

import logging
import os
import signal
import shutil
import subprocess as _subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fmriflow.server.services.run_registry import RunRegistry, RunStateFile

logger = logging.getLogger(__name__)


@dataclass
class ConvertRunHandle:
    """Tracks a running DICOM-to-BIDS conversion job.

    Detach-reattach bookkeeping lives at the bottom of the dataclass.
    """
    run_id: str
    subject: str
    status: str = "running"  # running, done, failed, cancelled, lost
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
            "manifest_path": self.manifest_path,
            "error": self.error,
            "log_path": self.log_path,
        }


class _BatchAwareRunHandle(ConvertRunHandle):
    """A ConvertRunHandle that also forwards events to a parent BatchRunHandle."""

    def __init__(self, job_id: str, parent: BatchRunHandle, **kwargs):
        super().__init__(**kwargs)
        self._job_id = job_id
        self._parent = parent

    def push_event(self, event: dict) -> None:
        super().push_event(event)
        tagged = {**event, "job_id": self._job_id}
        self._parent.push_event(tagged)


@dataclass
class BatchJobHandle:
    """Tracks a single job within a batch conversion."""
    job_id: str
    subject: str
    session: str
    status: str = "queued"  # queued, running, done, failed
    run_handle: ConvertRunHandle | None = None
    error: str | None = None
    started_at: float = 0.0
    finished_at: float = 0.0


@dataclass
class BatchRunHandle:
    """Tracks a batch of DICOM-to-BIDS conversion jobs."""
    batch_id: str
    jobs: dict[str, BatchJobHandle] = field(default_factory=dict)
    status: str = "running"  # running, done
    events: list[dict] = field(default_factory=list)
    _pending: list[dict] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    started_at: float = 0.0
    finished_at: float = 0.0

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

    @property
    def summary(self) -> dict[str, Any]:
        counts = {"queued": 0, "running": 0, "done": 0, "failed": 0}
        for jh in self.jobs.values():
            counts[jh.status] = counts.get(jh.status, 0) + 1
        return {
            "batch_id": self.batch_id,
            "status": self.status,
            "n_jobs": len(self.jobs),
            "counts": counts,
            "jobs": [
                {
                    "job_id": jh.job_id,
                    "subject": jh.subject,
                    "session": jh.session,
                    "status": jh.status,
                    "error": jh.error,
                    "started_at": jh.started_at,
                    "finished_at": jh.finished_at,
                }
                for jh in self.jobs.values()
            ],
        }


class ConvertManager:
    """Manages heuristic discovery, manifest scanning, and conversion runs."""

    def __init__(
        self,
        heuristics_dir: Path | None = None,
        registry: RunRegistry | None = None,
    ):
        self.heuristics_dir = heuristics_dir
        self._manifests_cache: list[dict] | None = None
        self._cache_time: float = 0
        self._cache_ttl = 10.0
        self.active_runs: dict[str, ConvertRunHandle] = {}
        self.active_batches: dict[str, BatchRunHandle] = {}
        self.registry = registry or RunRegistry()

        try:
            self._reattach_active_runs()
        except Exception:
            logger.warning("Failed to scan convert run registry on startup", exc_info=True)

    # ── Heuristics ────────────────────────────────────────────────

    def list_heuristics(self) -> list[dict]:
        """List registered heuristics with metadata."""
        from fmriflow.convert.heuristics import list_heuristics

        results = []
        for info in list_heuristics():
            results.append({
                "name": info.name,
                "description": info.description,
                "scanner_pattern": info.scanner_pattern,
                "version": info.version,
                "tasks": info.tasks,
                "path": str(info.path),
            })
        return results

    # ── Tool availability ────────────────────────────────────────

    def check_tools(self) -> list[dict]:
        """Check availability of conversion-related tools."""
        tools = []

        # heudiconv
        heudiconv_path = shutil.which("heudiconv")
        if heudiconv_path:
            version = "unknown"
            try:
                import subprocess
                result = subprocess.run(
                    ["heudiconv", "--version"],
                    capture_output=True, text=True, timeout=10,
                )
                version = (result.stdout.strip() or result.stderr.strip()) or "unknown"
            except Exception:
                pass
            tools.append({
                "name": "heudiconv",
                "available": True,
                "detail": f"version {version}",
            })
        else:
            tools.append({
                "name": "heudiconv",
                "available": False,
                "detail": "heudiconv not found. Install via: pip install heudiconv",
            })

        # dcm2niix (runtime dependency of heudiconv)
        dcm2niix_path = shutil.which("dcm2niix")
        if dcm2niix_path:
            version = "unknown"
            try:
                import subprocess
                result = subprocess.run(
                    ["dcm2niix", "--version"],
                    capture_output=True, text=True, timeout=10,
                )
                version = (result.stdout.strip().split("\n")[0] or
                           result.stderr.strip().split("\n")[0] or "unknown")
            except Exception:
                pass
            tools.append({
                "name": "dcm2niix",
                "available": True,
                "detail": f"{version} (used by heudiconv)",
            })
        else:
            tools.append({
                "name": "dcm2niix",
                "available": False,
                "detail": "dcm2niix not found. Install via: conda install -c conda-forge dcm2niix",
            })

        # pydicom
        try:
            import pydicom
            tools.append({
                "name": "pydicom",
                "available": True,
                "detail": f"version {pydicom.__version__}",
            })
        except ImportError:
            tools.append({
                "name": "pydicom",
                "available": False,
                "detail": "pydicom not installed. Install via: pip install pydicom",
            })

        # nibabel
        try:
            import nibabel as nib
            tools.append({
                "name": "nibabel",
                "available": True,
                "detail": f"version {nib.__version__}",
            })
        except ImportError:
            tools.append({
                "name": "nibabel",
                "available": False,
                "detail": "nibabel not installed. Install via: pip install nibabel",
            })

        # bids-validator
        bids_val_path = shutil.which("bids-validator")
        if bids_val_path:
            tools.append({
                "name": "bids-validator",
                "available": True,
                "detail": "available",
            })
        else:
            tools.append({
                "name": "bids-validator",
                "available": False,
                "detail": "bids-validator not found. Install via: npm install -g bids-validator",
            })

        return tools

    # ── Manifest scanning ────────────────────────────────────────

    def scan_manifests(self) -> list[dict]:
        """Scan for convert_manifest.json files in the current working directory."""
        now = time.time()
        if self._manifests_cache is not None and (now - self._cache_time) < self._cache_ttl:
            return self._manifests_cache

        manifests = []
        cwd = Path.cwd()

        for mf in sorted(cwd.rglob("convert_manifest.json")):
            try:
                from fmriflow.convert.manifest import ConvertManifest
                m = ConvertManifest.from_json(mf)
                manifests.append({
                    "subject": m.subject,
                    "path": str(mf),
                    "dataset": m.dataset,
                    "sessions": m.sessions,
                    "n_runs": len(m.runs),
                    "bids_dir": m.bids_dir,
                    "bids_valid": m.bids_valid,
                    "heudiconv_version": m.heudiconv_version,
                    "created": m.created,
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
                    from fmriflow.convert.manifest import ConvertManifest
                    manifest = ConvertManifest.from_json(m["path"])
                    return manifest.to_dict()
                except Exception:
                    return None
        return None

    def validate_manifest(self, subject: str) -> dict:
        """Validate a convert manifest for a subject."""
        manifests = self.scan_manifests()
        path = None
        for m in manifests:
            if m["subject"] == subject:
                path = m["path"]
                break
        if path is None:
            return {"errors": [f"No manifest found for subject '{subject}'"]}

        from fmriflow.convert.manifest import ConvertManifest
        from fmriflow.convert.validation import validate_manifest

        manifest = ConvertManifest.from_json(path)
        errors = validate_manifest(manifest)
        return {"errors": errors}

    # ── Collect ──────────────────────────────────────────────────

    def collect(self, params: dict) -> dict:
        """Collect existing BIDS outputs into a manifest."""
        from fmriflow.convert.manifest import ConvertConfig
        from fmriflow.convert.runner import collect_bids

        config = ConvertConfig(
            source_dir=params.get("source_dir", ""),
            subject=params["subject"],
            bids_dir=params["bids_dir"],
            heuristic=params.get("heuristic", ""),
            sessions=params.get("sessions"),
            dataset_name=params.get("dataset_name"),
        )

        manifest = collect_bids(config)
        self.invalidate_cache()

        manifest_path = Path(config.bids_dir) / "convert_manifest.json"
        manifest.save(manifest_path)

        return {
            "manifest": manifest.to_dict(),
            "manifest_path": str(manifest_path),
        }

    # ── Run conversion ───────────────────────────────────────────

    def start_run(self, params: dict) -> str:
        """Start a DICOM-to-BIDS conversion in a background thread."""
        run_id = f"convert_{params['subject']}_{uuid.uuid4().hex[:8]}"
        now = time.time()

        handle = ConvertRunHandle(
            run_id=run_id,
            subject=params["subject"],
            started_at=now,
            params=params,
        )

        # Pre-register so that even if spawn fails there's a record on disk.
        state = RunStateFile(
            run_id=run_id,
            kind="convert",
            backend="heudiconv",
            subject=params["subject"],
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
            name=f"convert-{run_id}",
        )
        thread.start()
        return run_id

    def _execute_run(self, handle: ConvertRunHandle, params: dict) -> None:
        """Drive a detached heudiconv subprocess and stream its log."""
        self._run_heudiconv_detached(handle, params)

    def _run_heudiconv_detached(
        self,
        handle: ConvertRunHandle,
        params: dict,
    ) -> None:
        """Spawn heudiconv detached, tail its log, finalize + save manifest.

        Used by both single-subject runs and each job in a batch.
        """
        from fmriflow.convert.errors import ConvertError, HeudiconvError
        from fmriflow.convert.manifest import ConvertConfig
        from fmriflow.convert.heuristics import resolve_heuristic
        from fmriflow.convert.runner import collect_bids, run_bids_validator

        log_path = Path(handle.log_path) if handle.log_path else None

        try:
            config = ConvertConfig(
                source_dir=params["source_dir"],
                subject=params["subject"],
                bids_dir=params["bids_dir"],
                heuristic=params["heuristic"],
                sessions=params.get("sessions"),
                dataset_name=params.get("dataset_name"),
                grouping=params.get("grouping"),
                minmeta=params.get("minmeta", False),
                overwrite=params.get("overwrite", True),
                validate_bids=params.get("validate_bids", True),
            )

            if not shutil.which("heudiconv"):
                raise ConvertError(
                    "heudiconv not found. Install via: pip install heudiconv",
                    subject=config.subject,
                )

            heuristic_path = resolve_heuristic(config.heuristic)
            cmd = [
                "heudiconv",
                "--files", config.source_dir,
                "-o", config.bids_dir,
                "-s", config.subject,
                "-f", str(heuristic_path),
                "--bids",
            ]
            if config.sessions:
                cmd.extend(["-ss", config.sessions[0]])
            if config.grouping:
                cmd.extend(["--grouping", config.grouping])
            if config.minmeta:
                cmd.append("--minmeta")
            if config.overwrite:
                cmd.append("--overwrite")

            Path(config.bids_dir).mkdir(parents=True, exist_ok=True)

            handle.push_event({
                "event": "started",
                "message": f"Starting heudiconv for sub-{config.subject}",
            })

            if log_path is None:
                # Fall back to in-process execution if we couldn't set up
                # a log file (defensive — happens only if registry init failed).
                proc = _subprocess.Popen(
                    cmd, stdout=_subprocess.PIPE, stderr=_subprocess.STDOUT, text=True,
                )
            else:
                log_fh = open(log_path, "w", buffering=1)
                proc = _subprocess.Popen(
                    cmd,
                    stdout=log_fh,
                    stderr=_subprocess.STDOUT,
                    text=True,
                    start_new_session=True,
                )

            handle.pid = proc.pid
            try:
                handle.pgid = os.getpgid(proc.pid)
            except OSError:
                handle.pgid = proc.pid
            self._persist_state(handle)

            tailer: _ConvertLogTailer | None = None
            if log_path is not None:
                tailer = _ConvertLogTailer(
                    log_path, handle, stop_when=lambda: proc.poll() is not None,
                )
                tailer.start()

            proc.wait()
            if tailer is not None:
                tailer.stop_and_join()

            if proc.returncode != 0:
                raise HeudiconvError(
                    f"heudiconv exited with code {proc.returncode}",
                    subject=config.subject,
                    returncode=proc.returncode,
                    stderr="",
                )

            manifest = collect_bids(config)
            if config.validate_bids:
                manifest = run_bids_validator(manifest)

            manifest_path = Path(config.bids_dir) / "convert_manifest.json"
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
            handle.status = "failed"
            handle.error = str(e)
            handle.finished_at = time.time()
            handle.push_event({
                "event": "failed",
                "error": str(e),
                "elapsed": handle.finished_at - handle.started_at,
            })
            logger.error("Conversion failed: %s", e, exc_info=True)

        finally:
            self._persist_state(handle)

    # ── DICOM scanning ───────────────────────────────────────────

    def scan_dicom(self, source_dir: str) -> dict:
        """Scan a DICOM directory for scanner info and series listing."""
        from fmriflow.convert.dicom_utils import extract_scanner_info, list_series
        from dataclasses import asdict

        scanner = extract_scanner_info(source_dir)
        series = list_series(source_dir)

        return {
            "scanner": asdict(scanner) if scanner else None,
            "series": [asdict(s) for s in series],
        }

    # ── Batch conversion ──────────────────────────────────────────

    def start_run_from_config_file(
        self,
        config_path: str,
        overrides: dict | None = None,
    ) -> dict:
        """Launch a single or batch conversion from a YAML file on disk.

        Decides based on the YAML's top-level shape:

        * If it contains ``convert_batch:`` or ``jobs:``, run as a batch
          and return ``{"batch_id": ...}``.
        * Otherwise run as a single subject and return ``{"run_id": ...}``.

        Non-None fields in ``overrides`` shallow-merge on top of the
        parsed config before launching.
        """
        import yaml

        path = Path(config_path)
        if not path.is_file():
            raise FileNotFoundError(f"Convert config not found: {path}")

        raw = path.read_text()
        data = yaml.safe_load(raw) or {}
        if not isinstance(data, dict):
            raise ValueError(f"Convert config '{path.name}' is not a mapping")

        data.pop("_meta", None)

        is_batch = "convert_batch" in data or "jobs" in data
        if is_batch:
            from fmriflow.convert.batch import parse_batch_yaml
            batch_config = parse_batch_yaml(raw)
            batch_id = self.start_batch(batch_config)
            return {"kind": "batch", "batch_id": batch_id}

        params = dict(data)
        if overrides:
            params.update({k: v for k, v in overrides.items() if v is not None})
        for field_name in ("source_dir", "bids_dir", "subject", "heuristic"):
            if not params.get(field_name):
                raise ValueError(
                    f"Convert config missing required field '{field_name}'"
                )
        run_id = self.start_run(params)
        return {"kind": "single", "run_id": run_id}

    def start_batch(self, batch_config) -> str:
        """Start a batch of DICOM-to-BIDS conversions."""
        from fmriflow.convert.batch import generate_job_id

        batch_id = f"batch_{uuid.uuid4().hex[:8]}"
        batch_handle = BatchRunHandle(
            batch_id=batch_id,
            started_at=time.time(),
        )

        for job in batch_config.jobs:
            job_id = generate_job_id(job)
            batch_handle.jobs[job_id] = BatchJobHandle(
                job_id=job_id,
                subject=job.subject,
                session=job.session,
            )

        self.active_batches[batch_id] = batch_handle

        thread = threading.Thread(
            target=self._batch_orchestrator,
            args=(batch_handle, batch_config),
            daemon=True,
        )
        thread.start()
        return batch_id

    def _batch_orchestrator(self, batch_handle: BatchRunHandle, batch_config) -> None:
        """Orchestrate parallel execution of batch jobs."""
        from fmriflow.convert.batch import generate_job_id

        batch_handle.push_event({
            "event": "batch_started",
            "n_jobs": len(batch_handle.jobs),
        })

        job_list = list(batch_handle.jobs.keys())
        job_configs = list(batch_config.jobs)

        # Map job_id -> BatchJobConfig
        job_map = dict(zip(job_list, job_configs))

        max_workers = min(batch_config.max_workers, len(job_list))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for job_id, job_cfg in zip(job_list, job_configs):
                job_handle = batch_handle.jobs[job_id]
                params = batch_config.to_convert_params(job_cfg)

                # Create a batch-aware run handle + register in the
                # shared run registry so the heudiconv subprocess survives
                # server restarts the same way single runs do. Batch
                # grouping is lost on reattach — each job re-appears as
                # a standalone convert run in the In-Flight panel.
                run_id = f"convert_{job_cfg.subject}_{uuid.uuid4().hex[:8]}"
                now = time.time()
                run_handle = _BatchAwareRunHandle(
                    job_id=job_id,
                    parent=batch_handle,
                    run_id=run_id,
                    subject=job_cfg.subject,
                    started_at=now,
                    params=params,
                )
                state = RunStateFile(
                    run_id=run_id,
                    kind="convert",
                    backend="heudiconv",
                    subject=job_cfg.subject,
                    status="running",
                    started_at=now,
                    params=params,
                )
                self.registry.register(state)
                run_handle.log_path = state.stdout_log

                job_handle.run_handle = run_handle
                self.active_runs[run_handle.run_id] = run_handle

                future = executor.submit(self._execute_batch_job, batch_handle, job_handle, run_handle, params)
                futures[future] = job_id

            for future in as_completed(futures):
                job_id = futures[future]
                try:
                    future.result()
                except Exception:
                    logger.error("Unexpected error in batch job %s", job_id, exc_info=True)

                # Push batch progress event
                batch_handle.push_event({
                    "event": "batch_progress",
                    **batch_handle.summary["counts"],
                })

        batch_handle.status = "done"
        batch_handle.finished_at = time.time()
        batch_handle.push_event({
            "event": "batch_done",
            "elapsed": batch_handle.finished_at - batch_handle.started_at,
            **batch_handle.summary["counts"],
        })
        self.invalidate_cache()

    def _execute_batch_job(
        self,
        batch_handle: BatchRunHandle,
        job_handle: BatchJobHandle,
        run_handle: ConvertRunHandle,
        params: dict,
    ) -> None:
        """Execute a single job within a batch."""
        job_handle.status = "running"
        job_handle.started_at = time.time()
        batch_handle.push_event({
            "event": "job_started",
            "job_id": job_handle.job_id,
            "subject": job_handle.subject,
            "session": job_handle.session,
        })

        self._execute_run(run_handle, params)

        job_handle.finished_at = time.time()
        if run_handle.status == "done":
            job_handle.status = "done"
        else:
            job_handle.status = "failed"
            job_handle.error = run_handle.error

    # ── Registry / reattach / cancel ──────────────────────────────────

    def _persist_state(self, handle: ConvertRunHandle) -> None:
        """Flush the handle back to the registry state file."""
        state = RunStateFile(
            run_id=handle.run_id,
            kind="convert",
            backend="heudiconv",
            subject=handle.subject,
            status=handle.status,
            pid=handle.pid,
            pgid=handle.pgid,
            started_at=handle.started_at,
            finished_at=handle.finished_at,
            stdout_log=handle.log_path or "",
            params=handle.params,
            error=handle.error,
            manifest_path=handle.manifest_path,
        )
        self.registry.update(state)

    def _reattach_active_runs(self) -> None:
        """On startup, scan the registry and rehydrate handles for live runs."""
        for state in self.registry.list_active():
            if state.kind != "convert":
                continue
            if not RunRegistry.pid_alive(state.pid):
                self.registry.mark_lost(state, "server_lost_track")
                continue

            handle = ConvertRunHandle(
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

            monitor = _ConvertReattachedMonitor(handle, self, state)
            thread = threading.Thread(
                target=monitor.run, daemon=True, name=f"reattach-convert-{state.run_id}",
            )
            thread.start()
            logger.info(
                "Reattached to convert run %s (pid=%s, subject=%s)",
                state.run_id, state.pid, state.subject,
            )

    def list_runs(self, include_finished: bool = True) -> list[dict]:
        """Return in-memory active runs plus (optionally) recent finished ones."""
        out: dict[str, dict] = {}
        for handle in self.active_runs.values():
            out[handle.run_id] = handle.to_summary()
        if include_finished:
            for state in self.registry.list_all():
                if state.kind != "convert" or state.run_id in out:
                    continue
                out[state.run_id] = {
                    "run_id": state.run_id,
                    "subject": state.subject,
                    "status": state.status,
                    "pid": state.pid,
                    "started_at": state.started_at,
                    "finished_at": state.finished_at,
                    "is_reattached": False,
                    "manifest_path": state.manifest_path,
                    "error": state.error,
                    "log_path": state.stdout_log,
                }
        return sorted(out.values(), key=lambda r: r.get("started_at") or 0, reverse=True)

    def get_run(self, run_id: str) -> dict | None:
        """Return summary + recent log tail for a run."""
        handle = self.active_runs.get(run_id)
        if handle is not None:
            summary = handle.to_summary()
        else:
            state = self.registry.load(run_id)
            if state is None or state.kind != "convert":
                return None
            summary = {
                "run_id": state.run_id,
                "subject": state.subject,
                "status": state.status,
                "pid": state.pid,
                "started_at": state.started_at,
                "finished_at": state.finished_at,
                "is_reattached": False,
                "manifest_path": state.manifest_path,
                "error": state.error,
                "log_path": state.stdout_log,
            }
        log_path = summary.get("log_path")
        summary["log_tail"] = _read_tail(log_path, n=200) if log_path else ""
        return summary

    def cancel_run(self, run_id: str) -> dict:
        """Terminate a running heudiconv subprocess. SIGTERM then SIGKILL."""
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

    def get_batch_status(self, batch_id: str) -> dict | None:
        """Return the summary for a batch."""
        handle = self.active_batches.get(batch_id)
        if handle is None:
            return None
        return handle.summary

    def retry_failed(self, batch_id: str):
        """Create a new batch from the failed jobs of a previous batch."""
        from fmriflow.convert.batch import BatchConfig, BatchJobConfig

        old = self.active_batches.get(batch_id)
        if old is None:
            raise ValueError(f"Batch '{batch_id}' not found")

        failed_jobs = [jh for jh in old.jobs.values() if jh.status == "failed"]
        if not failed_jobs:
            raise ValueError("No failed jobs to retry")

        # We need to reconstruct job configs from the run handles' params
        # For simplicity, look at the original run handle params
        new_jobs = []
        for jh in failed_jobs:
            rh = jh.run_handle
            if rh is None:
                continue
            new_jobs.append(BatchJobConfig(
                subject=jh.subject,
                source_dir="",  # will be filled from events
                session=jh.session,
            ))

        # Get the shared params from the first event of the old batch
        # In practice, the caller should provide the original config
        # For retry, we return the failed job IDs and let the client re-submit
        return {
            "failed_jobs": [
                {"job_id": jh.job_id, "subject": jh.subject, "session": jh.session, "error": jh.error}
                for jh in failed_jobs
            ]
        }


class _LogCapture(logging.Handler):
    """Logging handler that pushes log records as events to a run handle."""

    def __init__(self, run_handle: ConvertRunHandle):
        super().__init__()
        self.run_handle = run_handle

    def emit(self, record: logging.LogRecord) -> None:
        self.run_handle.push_event({
            "event": "log",
            "message": self.format(record),
        })


# ── Log tailer + reattached monitor (convert-flavoured) ─────────────────


class _ConvertLogTailer(threading.Thread):
    """Reads new lines from a heudiconv log file and pushes them as events."""

    def __init__(
        self,
        log_path: Path,
        handle: ConvertRunHandle,
        stop_when,
        poll_interval: float = 0.5,
    ):
        super().__init__(daemon=True, name=f"convert-tail-{handle.run_id}")
        self.log_path = log_path
        self.handle = handle
        self.stop_when = stop_when
        self.poll_interval = poll_interval
        self._stop = threading.Event()

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
                    if self._stop.is_set() or self.stop_when():
                        tail = f.read()
                        if tail:
                            for ln in tail.splitlines():
                                self._emit(ln)
                        return
                    time.sleep(self.poll_interval)
        except Exception:
            logger.warning("Convert log tailer crashed for %s", self.handle.run_id, exc_info=True)

    def _emit(self, line: str) -> None:
        self.handle.push_event({"event": "log", "message": line})

    def stop_and_join(self, timeout: float = 2.0) -> None:
        self._stop.set()
        self.join(timeout=timeout)


class _ConvertReattachedMonitor:
    """Tails the log file of a reattached convert run and watches its PID.

    When the PID dies, inspect the BIDS output dir for the subject's
    convert_manifest.json (written by a successful collect_bids step) —
    present → done (manifest loaded back); missing → failed.
    """

    def __init__(
        self,
        handle: ConvertRunHandle,
        manager: "ConvertManager",
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
            tailer = _ConvertLogTailer(log_path, self.handle, stop_when=stop_when)
            tailer.start()

        while RunRegistry.pid_alive(self.handle.pid):
            time.sleep(1.0)
        proc_dead.set()

        if tailer is not None:
            tailer.stop_and_join()

        self._finalize()

    def _finalize(self) -> None:
        params = self.state.params or {}
        bids_dir = params.get("bids_dir")
        now = time.time()

        manifest_path = None
        if bids_dir:
            candidate = Path(bids_dir) / "convert_manifest.json"
            if candidate.is_file():
                manifest_path = str(candidate)

        if manifest_path:
            self.handle.status = "done"
            self.handle.finished_at = now
            self.handle.manifest_path = manifest_path
            self.handle.push_event({
                "event": "done",
                "message": "convert_manifest.json found after reattach",
                "manifest_path": manifest_path,
                "elapsed": now - self.handle.started_at,
            })
        else:
            # heudiconv may have produced a partial BIDS tree without the
            # manifest if the parent died mid-collect_bids. Mark as failed
            # for safety; the user can re-run collect from the Collect tab.
            self.handle.status = "failed"
            self.handle.error = "subprocess exited without a complete convert_manifest.json"
            self.handle.finished_at = now
            self.handle.push_event({
                "event": "failed",
                "error": self.handle.error,
                "elapsed": now - self.handle.started_at,
            })

        self.manager._persist_state(self.handle)
        self.manager.invalidate_cache()


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
