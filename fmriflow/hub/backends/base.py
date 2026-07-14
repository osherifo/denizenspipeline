"""Transport-backend Protocol for hub sources.

A backend only moves bytes: sync a source into a local clone dir, and push
a contribution back. The catalog/manifest/install logic sits above it and is
backend-agnostic, so adding a `dir`/`http`/`s3` backend is self-contained.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


class BackendError(RuntimeError):
    """A transport operation failed (with a user-facing message)."""


@runtime_checkable
class HubBackend(Protocol):
    def preflight(self) -> list[str]:
        """Return a list of missing-prerequisite messages ([] if ready)."""
        ...

    def sync(self, url: str, branch: str, dest: Path, token: str | None) -> None:
        """Clone or update *url*@*branch* into *dest* (incl. LFS blobs)."""
        ...

    def publish(self, url: str, base_branch: str, dest: Path, token: str | None,
                push_branch: str, message: str) -> dict:
        """Commit staged changes in *dest* and push to *push_branch*.

        Returns ``{"branch": ..., "pushed": bool, "pr_url": str | None}``.
        """
        ...
