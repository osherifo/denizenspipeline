"""Preprocessing backends — wrappers for fmriprep, nipype, custom, etc.

Each backend implements the PreprocBackend protocol.
"""

from __future__ import annotations

from typing import Protocol

from fmriflow.preproc.errors import BackendNotFoundError
from fmriflow.preproc.manifest import (
    PreprocConfig,
    PreprocManifest,
    PreprocStatus,
)


class PreprocBackend(Protocol):
    """Wraps a preprocessing tool (fmriprep, AFNI, custom, etc.)."""

    name: str

    def run(self, config: PreprocConfig) -> PreprocManifest:
        """Run preprocessing and return a manifest of outputs."""
        ...

    def validate(self, config: PreprocConfig) -> list[str]:
        """Validate that the backend can run with the given config."""
        ...

    def status(self, config: PreprocConfig) -> PreprocStatus:
        """Check the status of a previously started run."""
        ...

    def collect(self, config: PreprocConfig) -> PreprocManifest:
        """Build a manifest from existing outputs without re-running."""
        ...


# ── Registry ─────────────────────────────────────────────────────────────

_BACKENDS: dict[str, type] = {}


def register_backend(name: str):
    """Decorator to register a backend class."""
    def wrapper(cls):
        _BACKENDS[name] = cls
        return cls
    return wrapper


def get_backend(name: str) -> PreprocBackend:
    """Instantiate and return a backend by name."""
    if name not in _BACKENDS:
        available = ", ".join(sorted(_BACKENDS)) or "(none)"
        raise BackendNotFoundError(
            f"Unknown preprocessing backend: '{name}'. "
            f"Available: {available}",
            backend=name,
            subject="",
        )
    return _BACKENDS[name]()


def list_backends() -> list[str]:
    """Return names of all registered backends."""
    return sorted(_BACKENDS)


# Import built-in backends so their @register_backend decorators fire
from fmriflow.preproc.backends import fmriprep as _fmriprep  # noqa: F401, E402
from fmriflow.preproc.backends import custom as _custom  # noqa: F401, E402
from fmriflow.preproc.backends import bids_app as _bids_app  # noqa: F401, E402
