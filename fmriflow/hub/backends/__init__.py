"""Hub transport backends. Only ``git`` is implemented; the Protocol in
``base`` keeps dir/http/s3 pluggable behind the same manifest contract."""

from __future__ import annotations

from fmriflow.hub.backends.base import HubBackend, BackendError
from fmriflow.hub.backends.git import GitBackend

__all__ = ["HubBackend", "BackendError", "GitBackend", "get_backend"]


def get_backend(kind: str) -> HubBackend:
    if kind == "git":
        return GitBackend()
    raise BackendError(f"Unknown hub backend '{kind}'")
