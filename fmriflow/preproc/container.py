"""Running command-line apps from a node.

Shared by the ``container_app`` nodes (fmriprep, bids_app, custom shell).
Apps run **bare**, straight from PATH — the full fMRIflow image ships
fmriprep, FreeSurfer and ANTs, and that is the supported deployment.
Launching an app inside its own docker / apptainer container is not
supported at present.

- :func:`run_logged` spawns the command in its own process group, streams
  stdout+stderr to a log file, hands every line to an optional callback
  (the fmriprep node feeds nipype's ``[Node]`` lines to the log parser so
  its inner DAG shows live), and kills the process group on a fatal
  marker or when :func:`terminate_children` is called (cancel).
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

# Lines that mean the app has already failed even though its worker pool
# keeps the process alive for a while (fmriprep's MultiProc plugin).
FATAL_MARKERS = (
    "fMRIPrep failed:",
    "recon-all: version check failed",
)

_LIVE_PGIDS: set[int] = set()
_LIVE_LOCK = threading.Lock()


# ── process management ────────────────────────────────────────────

def _register(pgid: int) -> None:
    with _LIVE_LOCK:
        _LIVE_PGIDS.add(pgid)


def _unregister(pgid: int) -> None:
    with _LIVE_LOCK:
        _LIVE_PGIDS.discard(pgid)


def terminate_children(sig: int = signal.SIGTERM) -> int:
    """Signal every live child process group; returns how many were signalled.

    The runner's SIGTERM handler calls this so a cancel reaches docker /
    apptainer children instead of orphaning them.
    """
    with _LIVE_LOCK:
        pgids = list(_LIVE_PGIDS)
    n = 0
    for pgid in pgids:
        try:
            os.killpg(pgid, sig)
            n += 1
        except ProcessLookupError:
            _unregister(pgid)
        except Exception:
            logger.warning("Failed to signal pgid=%s", pgid, exc_info=True)
    return n


def run_logged(
    cmd: list[str] | str,
    log_path: Path,
    *,
    shell: bool = False,
    on_line: Callable[[str], None] | None = None,
    fatal_markers: Iterable[str] = FATAL_MARKERS,
    poll_interval: float = 0.5,
    env: dict[str, str] | None = None,
    abort_event: threading.Event | None = None,
) -> int:
    """Run ``cmd`` detached in its own process group, logging to ``log_path``.

    Returns the exit code. Every new log line goes to ``on_line`` (called
    from a tailer thread). A line containing a fatal marker SIGTERMs the
    process group, so a failed fmriprep does not sit "running" for minutes.
    Setting ``abort_event`` (e.g. a ``bad`` checkpoint with abort opted in)
    does the same.
    """
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    markers = tuple(fatal_markers)

    with open(log_path, "w", buffering=1) as log_fh:
        proc = subprocess.Popen(
            cmd,
            shell=shell,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
            env=env,
        )
    pgid = proc.pid
    _register(pgid)
    stop = threading.Event()
    fatal_fired = threading.Event()

    def _tail() -> None:
        pos = 0
        while True:
            try:
                with open(log_path, "r", errors="replace") as fh:
                    fh.seek(pos)
                    for line in fh:
                        if not line.endswith("\n"):
                            # Partial line — wait for the rest.
                            break
                        pos += len(line.encode("utf-8", errors="replace"))
                        text = line.rstrip("\r\n")
                        if on_line is not None:
                            try:
                                on_line(text)
                            except Exception:
                                logger.debug("on_line callback failed", exc_info=True)
                        if markers and not fatal_fired.is_set() and any(m in text for m in markers):
                            fatal_fired.set()
                            logger.error("fatal marker in %s; terminating pgid=%s", log_path, pgid)
                            try:
                                os.killpg(pgid, signal.SIGTERM)
                            except ProcessLookupError:
                                pass
            except FileNotFoundError:
                pass
            if abort_event is not None and abort_event.is_set() and not fatal_fired.is_set():
                fatal_fired.set()
                logger.error("abort requested; terminating pgid=%s", pgid)
                try:
                    os.killpg(pgid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            if stop.is_set() and (not log_path.exists() or pos >= log_path.stat().st_size):
                return
            time.sleep(poll_interval)

    tailer = threading.Thread(target=_tail, daemon=True, name=f"tail-{log_path.stem}")
    tailer.start()
    try:
        returncode = proc.wait()
    finally:
        stop.set()
        tailer.join(timeout=5)
        _unregister(pgid)
    return returncode
