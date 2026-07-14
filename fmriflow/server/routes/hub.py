"""Artifact Hub endpoints — sources, catalog, install, publish.

Thin HTTP layer over ``app.state.hub`` (a :class:`fmriflow.hub.HubService`).
The hub is decoupled and optional; these routes are additive.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(tags=["hub"], prefix="/hub")


def _hub(request: Request):
    hub = getattr(request.app.state, "hub", None)
    if hub is None:
        raise HTTPException(status_code=503, detail="Artifact hub is unavailable")
    return hub


# ── Sources ──

class AddSourceBody(BaseModel):
    name: str
    url: str
    tier: str = "lab"          # "lab" | "community"
    branch: str = "main"
    backend: str = "git"
    token: str | None = None


class TokenBody(BaseModel):
    token: str | None = None


@router.get("/sources")
def get_sources(request: Request) -> dict:
    return _hub(request).sources_snapshot()


@router.post("/sources")
def add_source(request: Request, body: AddSourceBody) -> dict:
    hub = _hub(request)
    try:
        src = hub.registry.add(body.name, body.url, tier=body.tier,
                               branch=body.branch, backend=body.backend)
        if body.token:
            hub.registry.set_token(src.id, body.token)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return hub.sources_snapshot()


@router.delete("/sources/{sid}")
def remove_source(request: Request, sid: str) -> dict:
    hub = _hub(request)
    try:
        hub.registry.remove(sid)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return hub.sources_snapshot()


@router.post("/sources/{sid}/token")
def set_token(request: Request, sid: str, body: TokenBody) -> dict:
    hub = _hub(request)
    hub.registry.set_token(sid, body.token)
    return hub.sources_snapshot()


@router.post("/sources/{sid}/sync")
def sync_source(request: Request, sid: str) -> dict:
    hub = _hub(request)
    try:
        return hub.sync(sid)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (RuntimeError, Exception) as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e))


# ── Catalog ──

@router.get("/catalog")
def get_catalog(request: Request, kind: str | None = None) -> dict:
    hub = _hub(request)
    items = hub.catalog(request.app.state, kind=kind)
    return {"items": items, "total": len(items)}


@router.get("/catalog/{sid}/{kind}/{name}")
def get_artifact(request: Request, sid: str, kind: str, name: str) -> dict:
    hub = _hub(request)
    try:
        return hub.artifact(sid, kind, name, request.app.state)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── Install / publish ──

class InstallBody(BaseModel):
    source_id: str
    kind: str
    name: str


class PublishBody(BaseModel):
    source_id: str
    kind: str
    name: str
    author: str = ""
    description: str = ""


@router.post("/install")
def install(request: Request, body: InstallBody) -> dict:
    hub = _hub(request)
    try:
        return hub.install(body.source_id, body.kind, body.name, request.app.state)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:  # noqa: BLE001 - InstallError etc.
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/publish")
def publish(request: Request, body: PublishBody) -> dict:
    hub = _hub(request)
    try:
        return hub.publish(body.source_id, body.kind, body.name, request.app.state,
                           author=body.author, description=body.description)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:  # noqa: BLE001 - PublishError / BackendError
        raise HTTPException(status_code=400, detail=str(e))
