"""API route modules."""

from __future__ import annotations

from fastapi import Request

from fmriflow.registry import ModuleRegistry


def _registry(request: Request) -> ModuleRegistry:
    """Get the shared ModuleRegistry from app state."""
    return request.app.state.registry
