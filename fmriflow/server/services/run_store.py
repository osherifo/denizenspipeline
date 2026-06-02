"""RunStore — indexes and queries historical pipeline runs."""

from __future__ import annotations

import hashlib
import logging
import os
import time
from pathlib import Path

from fmriflow.core.run_summary import RunSummary

logger = logging.getLogger(__name__)


class RunStore:
    """Indexes run_summary.json files from a results directory."""

    def __init__(self, results_dir: Path):
        self.results_dir = results_dir
        self._index: list[dict] = []
        self._last_scan = 0.0

    def scan(self) -> None:
        """Re-scan results directory for run_summary.json files.

        Uses ``os.walk(followlinks=True)`` rather than ``Path.rglob`` so
        directory symlinks under ``results_dir`` are descended into.
        Per-subject runs from a group-orchestrator run are surfaced this
        way (symlinked from ``group_runs/<gn>/<run_id>/subjects/<sub>/``)
        until the proper group-runs integration lands (board #27).
        """
        self._index = []
        if not self.results_dir.is_dir():
            return

        visited: set[str] = set()  # guard against symlink cycles
        for dirpath, _dirnames, filenames in os.walk(
            self.results_dir, followlinks=True
        ):
            try:
                real = os.path.realpath(dirpath)
            except OSError:
                continue
            if real in visited:
                continue
            visited.add(real)

            if 'run_summary.json' not in filenames:
                continue
            summary_path = Path(dirpath) / 'run_summary.json'
            try:
                summary = RunSummary.from_json(summary_path)
                run_id = hashlib.md5(
                    str(summary_path.parent).encode()
                ).hexdigest()[:12]
                self._index.append({
                    'run_id': run_id,
                    'output_dir': str(summary_path.parent),
                    'summary': summary,
                })
            except Exception as e:
                logger.debug("Skipping %s: %s", summary_path, e)
                continue

        self._index.sort(
            key=lambda x: x['summary'].started_at, reverse=True
        )
        self._last_scan = time.time()

    def _maybe_rescan(self) -> None:
        """Re-scan if cache is stale (>5s)."""
        if time.time() - self._last_scan > 5.0:
            self.scan()

    def list_runs(
        self,
        limit: int = 50,
        experiment: str | None = None,
        subject: str | None = None,
    ) -> list[dict]:
        """Return matching runs, newest first."""
        self._maybe_rescan()
        runs = self._index
        if experiment:
            runs = [r for r in runs if r['summary'].experiment == experiment]
        if subject:
            runs = [r for r in runs if r['summary'].subject == subject]
        return runs[:limit]

    def get_run(self, run_id: str) -> dict | None:
        """Get a run by its ID."""
        self._maybe_rescan()
        for run in self._index:
            if run['run_id'] == run_id:
                return run
        return None
