"""Running containerised or bare command-line apps from a node.

Shared by the ``container_app`` nodes (fmriprep, bids_app, custom shell):

- :func:`container_prefix` builds the ``docker run`` / ``apptainer run``
  prefix with the standard ``/data`` ``/out`` ``/work`` binds.
- :func:`run_logged` spawns the command in its own process group, streams
  stdout+stderr to a log file, hands every line to an optional callback
  (the fmriprep node feeds nipype's ``[Node]`` lines to the log parser so
  its inner DAG shows live), and kills the process group on a fatal
  marker or when :func:`terminate_children` is called (cancel).
"""

from __future__ import annotations

import logging
import os
import shutil
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, Iterable

logger = logging.getLogger(__name__)

SINGULARITY_CONTAINER_TYPES = ("singularity", "apptainer")
VALID_CONTAINER_TYPES = ("singularity", "apptainer", "docker", "bare")

# Lines that mean the app has already failed even though its worker pool
# keeps the process alive for a while (fmriprep's MultiProc plugin).
FATAL_MARKERS = (
    "fMRIPrep failed:",
    "recon-all: version check failed",
)

_LIVE_PGIDS: set[int] = set()
_LIVE_LOCK = threading.Lock()


def singularity_binary() -> str | None:
    """``$FMRIFLOW_SINGULARITY_BIN`` > ``apptainer`` > ``singularity`` on PATH."""
    override = os.environ.get("FMRIFLOW_SINGULARITY_BIN")
    if override and Path(override).exists():
        return override
    return shutil.which("apptainer") or shutil.which("singularity")


def runtime_available(container: str | None, container_type: str) -> bool:
    """Can this host launch ``container`` the requested way?"""
    if not container or container_type == "bare":
        return True
    if container_type == "docker":
        return shutil.which("docker") is not None
    if container_type in SINGULARITY_CONTAINER_TYPES:
        if singularity_binary() is None:
            return False
        if container.startswith(("docker://", "library://", "shub://")):
            return True
        return Path(container).exists()
    return False


def container_prefix(
    container: str,
    container_type: str,
    *,
    bids_dir: str,
    output_dir: str,
    work_dir: str | None = None,
    extra_binds: Iterable[tuple[str, str]] = (),
) -> list[str]:
    """``docker run`` / ``apptainer run`` prefix ending with the image name.

    The BIDS root is bound read-only at ``/data``, outputs at ``/out`` and
    the work dir (if any) at ``/work``; ``extra_binds`` are ``(host, guest)``
    pairs bound read-write. The caller appends the app's own positional
    arguments using the *guest* paths.
    """
    binds: list[tuple[str, str, bool]] = [(bids_dir, "/data", True), (output_dir, "/out", False)]
    if work_dir:
        binds.append((work_dir, "/work", False))
    binds += [(h, g, False) for h, g in extra_binds]

    if container_type in SINGULARITY_CONTAINER_TYPES:
        cmd = [singularity_binary() or "singularity", "run", "--cleanenv"]
        for host, guest, ro in binds:
            cmd += ["-B", f"{host}:{guest}{':ro' if ro else ''}"]
    elif container_type == "docker":
        cmd = ["docker", "run", "--rm"]
        for host, guest, ro in binds:
            cmd += ["-v", f"{host}:{guest}{':ro' if ro else ''}"]
    else:
        raise ValueError(f"Unknown container_type: {container_type!r}")
    cmd.append(container)
    return cmd


def guest_paths(container_type: str, *, bids_dir: str, output_dir: str, work_dir: str | None) -> tuple[str, str, str | None]:
    """The paths an app sees for (bids, out, work): guest paths in a container, host paths bare."""
    if container_type == "bare":
        return bids_dir, output_dir, work_dir
    return "/data", "/out", ("/work" if work_dir else None)


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
) -> int:
    """Run ``cmd`` detached in its own process group, logging to ``log_path``.

    Returns the exit code. Every new log line goes to ``on_line`` (called
    from a tailer thread). A line containing a fatal marker SIGTERMs the
    process group, so a failed fmriprep does not sit "running" for minutes.
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
