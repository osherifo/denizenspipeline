"""File-handler context managers for capturing logger output to per-run files.

Solves a real diagnostic gap exposed by group runs: warnings from inside
reporters (e.g. ``flatmap`` skipping due to a pycortex mask/voxel mismatch)
went nowhere because the group orchestrator didn't set up file logging per
subject. ``capture_logs_to(path)`` adds a temporary :class:`FileHandler` to
the root logger so every ``logger.warning`` / ``logger.error`` lands on disk.

Both the group orchestrator (one ``group.log`` per group run) and each
subject's pipeline (``pipeline.log`` per subject) use this.
"""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


_FORMAT = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
_DATEFMT = '%Y-%m-%d %H:%M:%S'


class _ThreadFilter(logging.Filter):
    """Pass only records emitted from a specific OS thread."""

    def __init__(self, thread_id: int):
        super().__init__()
        self.thread_id = thread_id

    def filter(self, record: logging.LogRecord) -> bool:
        return record.thread == self.thread_id


@contextmanager
def capture_logs_to(
    path: Path,
    *,
    thread_local: bool = False,
    mode: str = 'w',
    level: int = logging.DEBUG,
) -> Iterator[Path]:
    """Tee root-logger records to ``path`` for the duration of the context.

    Parameters
    ----------
    path
        Log file. Parent directories are created automatically.
    thread_local
        If True, only records emitted from the calling thread are written.
        Used by the group orchestrator so a per-subject log doesn't catch
        other subjects' messages when ``parallel.max_workers > 1``.
    mode
        File-open mode. ``'w'`` replaces any previous log; ``'a'`` appends.
    level
        Minimum level captured. The root logger's effective level is
        temporarily lowered if needed so that the handler can see records.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # encoding='utf-8' is load-bearing: many fmriflow log messages contain
    # em-dashes / arrows / unicode separators. The FileHandler default
    # uses locale.getpreferredencoding(), which is ASCII when LANG=C — that
    # would emit a UnicodeEncodeError traceback for every such record.
    handler = logging.FileHandler(path, mode=mode, encoding='utf-8')
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATEFMT))
    if thread_local:
        handler.addFilter(_ThreadFilter(threading.get_ident()))

    root = logging.getLogger()
    root.addHandler(handler)

    prev_level = root.level
    # logging.NOTSET (0) means "inherit", which on the root logger acts like
    # WARNING. Bump to the requested capture level if we'd otherwise filter.
    if prev_level == logging.NOTSET or prev_level > level:
        root.setLevel(level)
    try:
        yield path
    finally:
        root.removeHandler(handler)
        handler.close()
        root.setLevel(prev_level)
