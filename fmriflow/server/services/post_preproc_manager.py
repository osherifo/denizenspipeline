"""Threaded post-preproc run manager.

v1 runs each graph in a background thread and tracks status in memory.
"""

from __future__ import annotations

import logging
import threading
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fmriflow.post_preproc.manifest import PostPreprocConfig
from fmriflow.post_preproc.runner import run_post_preproc

logger = logging.getLogger(__name__)


@dataclass
class PostPreprocRunHandle:
    run_id: str
    status: str = "pending"  # pending | running | done | failed
    error: str | None = None
    output_dir: str = ""
    manifest: dict[str, Any] | None = None
    config: dict[str, Any] = field(default_factory=dict)


class PostPreprocManager:
    """In-memory tracker for post-preproc runs."""

    def __init__(self):
        self._runs: dict[str, PostPreprocRunHandle] = {}
        self._lock = threading.Lock()

    def start(self, config: PostPreprocConfig, registry) -> PostPreprocRunHandle:
        run_id = uuid.uuid4().hex[:12]
        handle = PostPreprocRunHandle(
            run_id=run_id,
            status="pending",
            output_dir=str(Path(config.output_dir) / run_id),
            config=config.__dict__,
        )
        with self._lock:
            self._runs[run_id] = handle

        cfg_with_run = PostPreprocConfig(
            subject=config.subject,
            source_manifest_path=config.source_manifest_path,
            graph=config.graph,
            output_dir=handle.output_dir,
            name=config.name,
        )

        thread = threading.Thread(
            target=self._run, args=(run_id, cfg_with_run, registry), daemon=True
        )
        thread.start()
        return handle

    def _run(self, run_id: str, config: PostPreprocConfig, registry) -> None:
        with self._lock:
            self._runs[run_id].status = "running"
        try:
            manifest = run_post_preproc(config, registry=registry)
            with self._lock:
                handle = self._runs[run_id]
                handle.status = "done"
                handle.manifest = manifest.to_dict()
        except Exception as e:
            logger.exception("post-preproc run %s failed", run_id)
            with self._lock:
                handle = self._runs[run_id]
                handle.status = "failed"
                handle.error = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"

    def get(self, run_id: str) -> PostPreprocRunHandle | None:
        with self._lock:
            return self._runs.get(run_id)

    def list(self) -> list[PostPreprocRunHandle]:
        with self._lock:
            return list(self._runs.values())
