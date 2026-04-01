"""Conversion manager — heuristic listing, manifest scanning, and run orchestration."""

from __future__ import annotations

import logging
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ConvertRunHandle:
    """Tracks a running DICOM-to-BIDS conversion job."""
    run_id: str
    subject: str
    status: str = "running"  # running, done, failed
    events: list[dict] = field(default_factory=list)
    _pending: list[dict] = field(default_factory=list)
    manifest_path: str | None = None
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

    def __init__(self, heuristics_dir: Path | None = None):
        self.heuristics_dir = heuristics_dir
        self._manifests_cache: list[dict] | None = None
        self._cache_time: float = 0
        self._cache_ttl = 10.0
        self.active_runs: dict[str, ConvertRunHandle] = {}
        self.active_batches: dict[str, BatchRunHandle] = {}

    # ── Heuristics ────────────────────────────────────────────────

    def list_heuristics(self) -> list[dict]:
        """List registered heuristics with metadata."""
        from denizenspipeline.convert.heuristics import list_heuristics

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
                from denizenspipeline.convert.manifest import ConvertManifest
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
                    from denizenspipeline.convert.manifest import ConvertManifest
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

        from denizenspipeline.convert.manifest import ConvertManifest
        from denizenspipeline.convert.validation import validate_manifest

        manifest = ConvertManifest.from_json(path)
        errors = validate_manifest(manifest)
        return {"errors": errors}

    # ── Collect ──────────────────────────────────────────────────

    def collect(self, params: dict) -> dict:
        """Collect existing BIDS outputs into a manifest."""
        from denizenspipeline.convert.manifest import ConvertConfig
        from denizenspipeline.convert.runner import collect_bids

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
        handle = ConvertRunHandle(
            run_id=run_id,
            subject=params["subject"],
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

    def _execute_run(self, handle: ConvertRunHandle, params: dict) -> None:
        """Execute conversion in a background thread."""
        import logging as _logging
        capture = _LogCapture(handle)
        convert_logger = _logging.getLogger("denizenspipeline.convert")
        convert_logger.addHandler(capture)

        try:
            from denizenspipeline.convert.manifest import ConvertConfig
            from denizenspipeline.convert.runner import run_conversion

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

            handle.push_event({
                "event": "started",
                "message": f"Starting heudiconv for sub-{config.subject}",
            })

            manifest = run_conversion(config)

            handle.manifest_path = str(
                Path(config.bids_dir) / "convert_manifest.json"
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
            convert_logger.removeHandler(capture)

    # ── DICOM scanning ───────────────────────────────────────────

    def scan_dicom(self, source_dir: str) -> dict:
        """Scan a DICOM directory for scanner info and series listing."""
        from denizenspipeline.convert.dicom_utils import extract_scanner_info, list_series
        from dataclasses import asdict

        scanner = extract_scanner_info(source_dir)
        series = list_series(source_dir)

        return {
            "scanner": asdict(scanner) if scanner else None,
            "series": [asdict(s) for s in series],
        }

    # ── Batch conversion ──────────────────────────────────────────

    def start_batch(self, batch_config) -> str:
        """Start a batch of DICOM-to-BIDS conversions."""
        from denizenspipeline.convert.batch import generate_job_id

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
        from denizenspipeline.convert.batch import generate_job_id

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

                # Create a batch-aware run handle
                run_handle = _BatchAwareRunHandle(
                    job_id=job_id,
                    parent=batch_handle,
                    run_id=f"convert_{job_cfg.subject}_{uuid.uuid4().hex[:8]}",
                    subject=job_cfg.subject,
                    started_at=time.time(),
                )
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

    def get_batch_status(self, batch_id: str) -> dict | None:
        """Return the summary for a batch."""
        handle = self.active_batches.get(batch_id)
        if handle is None:
            return None
        return handle.summary

    def retry_failed(self, batch_id: str):
        """Create a new batch from the failed jobs of a previous batch."""
        from denizenspipeline.convert.batch import BatchConfig, BatchJobConfig

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
