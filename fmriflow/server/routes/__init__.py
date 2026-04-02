"""API route modules."""

from __future__ import annotations

from fastapi import Request

from fmriflow.registry import PluginRegistry


def _registry(request: Request) -> PluginRegistry:
    """Get the shared PluginRegistry from app state."""
    return request.app.state.registry
