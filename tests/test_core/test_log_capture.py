"""Tests for fmriflow.core.log_capture."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from fmriflow.core.log_capture import capture_logs_to


def test_writes_records_to_file(tmp_path: Path):
    log_path = tmp_path / "run.log"
    log = logging.getLogger("fmriflow.test.basic")
    with capture_logs_to(log_path):
        log.warning("hello-warning")
        log.info("hello-info")
    text = log_path.read_text()
    assert "hello-warning" in text
    assert "hello-info" in text


def test_removes_handler_after_exit(tmp_path: Path):
    log_path = tmp_path / "run.log"
    root = logging.getLogger()
    before = list(root.handlers)
    with capture_logs_to(log_path):
        pass
    after = list(root.handlers)
    assert before == after, "FileHandler should be removed on context exit"


def test_thread_local_filters_other_threads(tmp_path: Path):
    """A thread-local capture must NOT record messages from another thread."""
    log_path = tmp_path / "mine.log"
    log = logging.getLogger("fmriflow.test.threaded")
    other_done = threading.Event()
    capture_started = threading.Event()

    def other_thread_work():
        capture_started.wait(timeout=2)
        log.warning("from-other-thread")
        other_done.set()

    t = threading.Thread(target=other_thread_work, daemon=True)
    t.start()
    with capture_logs_to(log_path, thread_local=True):
        capture_started.set()
        other_done.wait(timeout=2)
        log.warning("from-main-thread")
    t.join(timeout=2)

    text = log_path.read_text()
    assert "from-main-thread" in text
    assert "from-other-thread" not in text


def test_root_level_restored(tmp_path: Path):
    root = logging.getLogger()
    prev = root.level
    try:
        root.setLevel(logging.WARNING)
        with capture_logs_to(tmp_path / "x.log", level=logging.DEBUG):
            # Inside the context, level may have been bumped to DEBUG.
            assert root.level <= logging.DEBUG
        # On exit it must restore to WARNING.
        assert root.level == logging.WARNING
    finally:
        root.setLevel(prev)


def test_append_mode(tmp_path: Path):
    log_path = tmp_path / "append.log"
    log = logging.getLogger("fmriflow.test.append")
    with capture_logs_to(log_path):
        log.warning("first")
    with capture_logs_to(log_path, mode="a"):
        log.warning("second")
    text = log_path.read_text()
    assert "first" in text and "second" in text
