"""Preprocessing error hierarchy."""

from __future__ import annotations


class PreprocError(Exception):
    """Base for all preprocessing errors."""

    def __init__(self, message: str, backend: str = "", subject: str = ""):
        self.backend = backend
        self.subject = subject
        super().__init__(message)


class BackendNotFoundError(PreprocError):
    """The preprocessing backend is not installed or not found."""


class BackendRunError(PreprocError):
    """The preprocessing backend failed during execution."""

    def __init__(
        self,
        message: str,
        backend: str,
        subject: str,
        returncode: int = -1,
        stderr: str = "",
    ):
        super().__init__(message, backend, subject)
        self.returncode = returncode
        self.stderr = stderr


class ManifestError(PreprocError):
    """Manifest is invalid, incomplete, or incompatible."""


class ConfoundsError(PreprocError):
    """Confound regression failed (missing columns, bad data, etc.)."""
