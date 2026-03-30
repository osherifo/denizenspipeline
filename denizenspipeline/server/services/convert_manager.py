"""Conversion manager — heuristic listing, manifest scanning, and run orchestration."""

from __future__ import annotations

import logging
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

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


class ConvertManager:
    """Manages heuristic discovery, manifest scanning, and conversion runs."""

    def __init__(self, heuristics_dir: Path | None = None):
        self.heuristics_dir = heuristics_dir
        self._manifests_cache: list[dict] | None = None
        self._cache_time: float = 0
        self._cache_ttl = 10.0
        self.active_runs: dict[str, ConvertRunHandle] = {}

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
