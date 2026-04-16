"""Module editor API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from fmriflow.server.services.module_loader import (
    validate_code,
    register_code,
    save_module,
    delete_module,
    list_user_modules,
    get_user_module_code,
)
from fmriflow.server.services.templates import render_template, TEMPLATES

router = APIRouter(prefix="/modules", tags=["editor"])


class ValidateCodeRequest(BaseModel):
    code: str
    category: str | None = None


class SaveModuleRequest(BaseModel):
    code: str
    name: str
    category: str


class TemplateRequest(BaseModel):
    category: str
    name: str


@router.post("/validate-code")
async def validate_module_code(req: ValidateCodeRequest):
    """Validate module code without saving."""
    result = validate_code(req.code, req.category)
    return result


@router.post("/save")
async def save_and_register(req: SaveModuleRequest):
    """Save a module to disk and register it in the live registry."""
    # Validate first
    validation = validate_code(req.code, req.category)
    if not validation['valid']:
        raise HTTPException(status_code=422, detail={
            'errors': validation['errors'],
            'warnings': validation['warnings'],
        })

    # Save to disk
    path = save_module(req.code, req.name, req.category)

    # Register in the live registry
    try:
        module_name, class_name, category = register_code(req.code)
    except ValueError as e:
        raise HTTPException(status_code=422, detail={'errors': [str(e)]})

    return {
        'saved': True,
        'path': str(path),
        'registered': True,
        'module_name': module_name,
        'class_name': class_name,
        'category': category,
    }


@router.get("/user")
async def list_user():
    """List all user-created modules."""
    return list_user_modules()


@router.get("/user/{name}")
async def get_user_module(name: str):
    """Return the source code for a user module."""
    code = get_user_module_code(name)
    if code is None:
        raise HTTPException(status_code=404, detail=f"User module '{name}' not found")
    return {'name': name, 'code': code}


@router.delete("/user/{name}")
async def delete_user_module(name: str):
    """Unregister and delete a user module."""
    deleted = delete_module(name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"User module '{name}' not found")
    return {'deleted': True, 'name': name}


@router.post("/template")
async def get_template(req: TemplateRequest):
    """Generate a module skeleton from a template."""
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
