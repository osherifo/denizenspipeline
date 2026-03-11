"""Plugin editor API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from denizenspipeline.server.services.plugin_loader import (
    validate_code,
    register_code,
    save_plugin,
    delete_plugin,
    list_user_plugins,
    get_user_plugin_code,
)
from denizenspipeline.server.services.templates import render_template, TEMPLATES

router = APIRouter(prefix="/plugins", tags=["editor"])


class ValidateCodeRequest(BaseModel):
    code: str
    category: str | None = None


class SavePluginRequest(BaseModel):
    code: str
    name: str
    category: str


class TemplateRequest(BaseModel):
    category: str
    name: str


@router.post("/validate-code")
async def validate_plugin_code(req: ValidateCodeRequest):
    """Validate plugin code without saving."""
    result = validate_code(req.code, req.category)
    return result


@router.post("/save")
async def save_and_register(req: SavePluginRequest):
    """Save a plugin to disk and register it in the live registry."""
    # Validate first
    validation = validate_code(req.code, req.category)
    if not validation['valid']:
        raise HTTPException(status_code=422, detail={
            'errors': validation['errors'],
            'warnings': validation['warnings'],
        })

    # Save to disk
    path = save_plugin(req.code, req.name, req.category)

    # Register in the live registry
    try:
        plugin_name, class_name, category = register_code(req.code)
    except ValueError as e:
        raise HTTPException(status_code=422, detail={'errors': [str(e)]})

    return {
        'saved': True,
        'path': str(path),
        'registered': True,
        'plugin_name': plugin_name,
        'class_name': class_name,
        'category': category,
    }


@router.get("/user")
async def list_user():
    """List all user-created plugins."""
    return list_user_plugins()


@router.get("/user/{name}")
async def get_user_plugin(name: str):
    """Return the source code for a user plugin."""
    code = get_user_plugin_code(name)
    if code is None:
        raise HTTPException(status_code=404, detail=f"User plugin '{name}' not found")
    return {'name': name, 'code': code}


@router.delete("/user/{name}")
async def delete_user_plugin(name: str):
    """Unregister and delete a user plugin."""
    deleted = delete_plugin(name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"User plugin '{name}' not found")
    return {'deleted': True, 'name': name}


@router.post("/template")
async def get_template(req: TemplateRequest):
    """Generate a plugin skeleton from a template."""
    try:
        code = render_template(req.category, req.name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        'code': code,
        'filename': f"{req.name}.py",
        'category': req.category,
    }


@router.get("/template-categories")
async def get_template_categories():
    """Return which categories have templates available."""
    return sorted(TEMPLATES.keys())
