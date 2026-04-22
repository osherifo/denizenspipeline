"""Preprocessing manager — manifest scanning, collect, and run orchestration."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class PreprocRunHandle:
    """Tracks a running preprocessing job."""
    run_id: str
    subject: str
    backend: str
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


class PreprocManager:
    """Manages manifest discovery and preprocessing runs."""

    def __init__(self, derivatives_dir: Path):
        self.derivatives_dir = derivatives_dir
        self._manifests_cache: list[dict] | None = None
        self._cache_time: float = 0
        self._cache_ttl = 10.0
        self.active_runs: dict[str, PreprocRunHandle] = {}

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

    def start_run(self, params: dict) -> str:
        """Start a preprocessing run in a background thread."""
        run_id = f"preproc_{params['subject']}_{uuid.uuid4().hex[:8]}"
        handle = PreprocRunHandle(
            run_id=run_id,
            subject=params["subject"],
            backend=params["backend"],
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

        return self.start_run(params)

    def _execute_run(self, handle: PreprocRunHandle, params: dict) -> None:
        """Execute preprocessing in a background thread."""
        import logging as _logging
        # Set up a handler that captures log lines as events
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
            handle.status = "failed"
            handle.error = str(e)
            handle.finished_at = time.time()
            handle.push_event({
                "event": "failed",
                "error": str(e),
                "elapsed": handle.finished_at - handle.started_at,
            })
            logger.error("Preprocessing failed: %s", e, exc_info=True)

        finally:
            preproc_logger.removeHandler(capture)

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
