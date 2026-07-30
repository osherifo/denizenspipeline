"""The blocking fmriprep run must drain the subprocess pipe.

``run()`` used to call ``proc.wait()`` while stdout was a pipe nobody
read. That deadlocks as soon as the OS pipe buffer fills (64 KB on
Linux) — which a real fmriprep run does within seconds — and on the
failure path it discarded every line of diagnostics, leaving the user
with nothing but an exit code.
"""

import subprocess
import sys

import pytest

from fmriflow.preproc.backends.fmriprep import FmriprepBackend
from fmriflow.preproc.errors import BackendRunError
from fmriflow.preproc.manifest import PreprocConfig

# Comfortably more than one pipe buffer.
CHATTY = "import sys\nfor i in range(20000): print('fmriprep log line', i)\n"


def _config():
    return PreprocConfig(
        subject="01", backend="fmriprep", bids_dir="/bids", output_dir="/out",
    )


@pytest.fixture
def backend(monkeypatch):
    b = FmriprepBackend()
    monkeypatch.setattr(FmriprepBackend, "collect", lambda self, config: "collected")
    return b


def _spawn_script(script, exit_code=0):
    body = script + f"sys.exit({exit_code})\n"

    def spawn(self, config, log_path):
        return subprocess.Popen(
            [sys.executable, "-c", body],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
    return spawn


def test_large_output_does_not_deadlock(backend, monkeypatch):
    """Old code hung here forever; the drain makes it complete."""
    monkeypatch.setattr(FmriprepBackend, "spawn", _spawn_script(CHATTY))

    assert backend.run(_config()) == "collected"


def test_failure_carries_the_tail_of_the_output(backend, monkeypatch):
    monkeypatch.setattr(FmriprepBackend, "spawn", _spawn_script(CHATTY, exit_code=1))

    with pytest.raises(BackendRunError) as excinfo:
        backend.run(_config())

    err = excinfo.value
    assert err.returncode == 1
    assert "fmriprep log line 19999" in err.stderr
    # Only a tail, not the whole 20k lines.
    assert err.stderr.count("\n") <= 50
