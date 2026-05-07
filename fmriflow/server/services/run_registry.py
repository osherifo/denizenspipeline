"""Filesystem-backed registry for long-running jobs.

Each run gets a directory under ``$FMRIFLOW_HOME/runs/{run_id}/``
(legacy ``~/.fmriflow/runs/`` is consulted as a read-only
fallback) containing:

- ``state.json`` — live status, pid, command, timestamps, config snapshot.
- ``stdout.log`` — the subprocess's captured stdout+stderr, tailed for
  event streaming and preserved after the run finishes.

The registry lets the server detach fmriprep subprocesses (via
``start_new_session=True``) and reattach to them after a server restart.
Only the preprocessing manager uses it today; the analysis run manager
can adopt the same pattern later.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from fmriflow.core import paths

logger = logging.getLogger(__name__)

STATE_FILENAME = "state.json"
STDOUT_FILENAME = "stdout.log"


@dataclass
class RunStateFile:
    """On-disk representation of one run.

    The schema is intentionally minimal so reattachment stays simple.
    Anything that requires re-parsing the config YAML lives in ``params``.
    """

    run_id: str
    kind: str                      # "preproc" | "run" (future)
    backend: str                   # "fmriprep", "custom", …
    subject: str
    status: str                    # "running" | "done" | "failed" | "cancelled" | "lost"
    pid: int | None = None
    pgid: int | None = None
    started_at: float = 0.0
    finished_at: float = 0.0
    stdout_log: str = ""
    config_path: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    manifest_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunStateFile:
        # Drop unknown keys so older state files don't crash on load.
        valid = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in valid})


class RunRegistry:
    """Directory-backed registry for preprocessing runs."""

    def __init__(self, root: Path | None = None):
        # Explicit root disables the legacy fallback (so tests are
        # isolated from the developer's real ~/.fmriflow/runs/).
        if root is not None:
            self.root = Path(root)
            self._legacy_root = None
        else:
            self.root = paths.runs_dir()
            self._legacy_root = paths.legacy_runs_root()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, run_id: str) -> Path:
        """Return the run directory, falling back to the legacy
        location for runs created before $FMRIFLOW_HOME existed."""
        new = self.root / run_id
        if new.is_dir() or self._legacy_root is None:
            return new
        legacy = self._legacy_root / run_id
        if legacy.is_dir():
            return legacy
        return new

    # ── Paths ────────────────────────────────────────────────────────

    def run_dir(self, run_id: str) -> Path:
        return self._resolve(run_id)

    def state_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / STATE_FILENAME

    def stdout_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / STDOUT_FILENAME

    # ── Create / update / load ──────────────────────────────────────

    def register(self, state: RunStateFile) -> Path:
        """Create the run directory and write the initial state file.

        New runs always go under ``self.root`` (the new home), even
        if a same-named legacy run exists.
        """
        d = self.root / state.run_id
        d.mkdir(parents=True, exist_ok=True)
        if not state.stdout_log:
            state.stdout_log = str(self.stdout_path(state.run_id))
        self._write(state)
        return d

    def update(self, state: RunStateFile) -> None:
        """Overwrite the state file for an existing run."""
        self._write(state)

    def load(self, run_id: str) -> RunStateFile | None:
        p = self.state_path(run_id)
        if not p.is_file():
            return None
        try:
            data = json.loads(p.read_text())
            return RunStateFile.from_dict(data)
        except Exception as e:
            logger.warning("Could not load state for %s: %s", run_id, e)
            return None

    def list_all(self) -> list[RunStateFile]:
        """Return every run currently on disk, newest first.

        Walks both the new root and the legacy ``~/.fmriflow/runs/``
        location so reattach works during the migration window.
        Legacy fallback is skipped when ``root`` was explicitly
        supplied (tests, custom registries).
        """
        out: list[RunStateFile] = []
        seen: set[str] = set()
        roots = [self.root]
        if self._legacy_root is not None:
            roots.append(self._legacy_root)
        for root in roots:
            if not root.is_dir():
                continue
            for child in root.iterdir():
                if not child.is_dir() or child.name in seen:
                    continue
                state = self.load(child.name)
                if state:
                    seen.add(child.name)
                    out.append(state)
        out.sort(key=lambda s: s.started_at, reverse=True)
        return out

    def list_active(self) -> list[RunStateFile]:
        """Return runs currently marked ``running``."""
        return [s for s in self.list_all() if s.status == "running"]

    # ── Liveness ────────────────────────────────────────────────────

    @staticmethod
    def pid_alive(pid: int | None) -> bool:
        """Return True if the given PID is alive.

        Uses ``os.kill(pid, 0)`` — sends no signal but raises if the
        process doesn't exist or we can't signal it.
        """
        if not pid or pid <= 0:
            return False
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            # Process exists but is owned by another user — still alive.
            return True
        except OSError:
            return False

    def mark_lost(self, state: RunStateFile, reason: str) -> None:
        """Mark a run as lost (server died while it was still running).

        Preserved on disk for later inspection.
        """
        state.status = "lost"
        state.error = reason
        state.finished_at = time.time()
        self._write(state)

    def delete(self, run_id: str) -> bool:
        """Recursively remove ``<root>/<run_id>/``.

        Refuses to delete anything whose resolved path escapes the
        registry root — defensive in case a caller ever passes a
        crafted run_id like ``../../foo``.

        Returns True if the directory existed and was removed, False
        if it was already absent.
        """
        import shutil

        rd = self.run_dir(run_id)
        try:
            resolved = rd.resolve(strict=False)
            root_resolved = self.root.resolve(strict=False)
        except OSError:
            return False
        if not resolved.is_relative_to(root_resolved):
            logger.warning(
                "Refusing to delete run_id %r: resolved path %s escapes registry root %s",
                run_id, resolved, root_resolved,
            )
            return False

        if not rd.is_dir():
            return False
        shutil.rmtree(rd, ignore_errors=False)
        return True

    # ── Internals ───────────────────────────────────────────────────

    def _write(self, state: RunStateFile) -> None:
        p = self.state_path(state.run_id)
        p.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write — write to tmp then rename.
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(state.to_dict(), indent=2))
        tmp.replace(p)
