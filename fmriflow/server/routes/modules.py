"""Module introspection endpoints."""

from __future__ import annotations

import importlib
import inspect
import traceback
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from fmriflow.core.stages import (
    GROUP_MODULE_STAGES,
    STAGE_MODULE_CATEGORIES,
    STUDY_MODULE_STAGES,
    SUBJECT_STAGES as ALL_STAGES,
)
from fmriflow.server.routes import _registry


class ModuleCodeBody(BaseModel):
    code: str

router = APIRouter(tags=["modules"])

STAGE_DESCRIPTIONS = {
    'stimuli': 'Load stimulus timing data (TextGrids, TRFiles)',
    'responses': 'Load fMRI response data',
    'features': 'Extract or load features from stimuli',
    'prepare': 'Trim, normalize, concatenate, delay',
    'model': 'Fit voxelwise encoding model',
    'analyze': 'Postprocessing analysis (variance partition, weights, etc.)',
    'report': 'Generate output artifacts (flatmaps, metrics, etc.)',
    'group_analyze': 'Reduce across subjects (means, second-pass injection, contrasts)',
    'group_report': 'Group-level reports (HTML, NPY dumps, fsaverage flatmaps)',
    'study_analyze': 'Reduce across groups (cross-modality contrasts, etc.)',
    'study_report': 'Study-level reports (HTML, combined figures)',
}


STAGE_COLORS = {
    'stimuli': '#00e5ff',
    'responses': '#e040fb',
    'features': '#ffd600',
    'prepare': '#00e676',
    'model': '#448aff',
    'analyze': '#ff1744',
    'report': '#ffffff',
    'group_analyze': '#ff1744',
    'group_report': '#ffffff',
    'study_analyze': '#ff1744',
    'study_report': '#ffffff',
}

# Group/study-scope orchestrators have plumbing stages (e.g.
# ``group_collect``, ``subject_second_pass``, ``study_collect``,
# ``groups_fanout``) that are orchestrator-only — they hold no
# user-pluggable modules and are intentionally omitted from
# /api/stages so the module browser doesn't show empty columns.
GROUP_STAGES = list(GROUP_MODULE_STAGES)
STUDY_STAGES = list(STUDY_MODULE_STAGES)

# stage_name → ``'subject' | 'group' | 'study'`` — drives the
# scope-tab filter in the frontend ModuleBrowser.
STAGE_SCOPE = {
    **{s: 'subject' for s in (
        'stimuli', 'responses', 'features', 'prepare',
        'model', 'analyze', 'report',
    )},
    **{s: 'group' for s in GROUP_STAGES},
    **{s: 'study' for s in STUDY_STAGES},
}


@router.get("/modules")
async def list_modules(request: Request):
    """Return all registered modules with their metadata."""
    registry = _registry(request)
    return registry.module_metadata()


@router.get("/modules/{category}/{name}")
async def get_module(request: Request, category: str, name: str):
    """Return detailed metadata for a single module."""
    registry = _registry(request)
    cls = registry.get_module_class(category, name)

    from fmriflow.modules._schema import extract_schema

    CATEGORY_TO_STAGE = {
        'stimulus_loaders': 'stimuli',
        'response_loaders': 'responses',
        'response_readers': 'responses',
        'feature_extractors': 'features',
        'feature_sources': 'features',
        'preparers': 'prepare',
        'preparation_steps': 'prepare',
        'analyzers': 'analyze',
        'models': 'model',
        'reporters': 'report',
    }

    doc = (cls.__doc__ or '').strip()
    entry = {
        'name': name,
        'docstring': doc.split('\n')[0] if doc else '',
        'full_docstring': doc,
        'category': category,
        'stage': CATEGORY_TO_STAGE.get(category, ''),
        'params': extract_schema(cls),
    }
    if hasattr(cls, 'n_dims'):
        entry['n_dims'] = cls.n_dims
    return entry


@router.get("/modules/{category}/{name}/code")
async def get_module_code(request: Request, category: str, name: str):
    """Return the Python source for a registered module.

    Returns the entire defining file (matches the heuristic /code endpoint),
    along with the line range of the class itself so the UI can highlight or
    scroll to it.
    """
    registry = _registry(request)
    try:
        cls = registry.get_module_class(category, name)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

    try:
        source_path = inspect.getsourcefile(cls)
    except TypeError:
        source_path = None
    if not source_path:
        raise HTTPException(
            status_code=404,
            detail=f"No source file for module '{name}' (likely defined dynamically)",
        )

    try:
        code = Path(source_path).read_text()
    except OSError as e:
        raise HTTPException(status_code=404, detail=f"Cannot read source: {e}")

    class_start: int | None = None
    class_end: int | None = None
    try:
        cls_lines, cls_lineno = inspect.getsourcelines(cls)
        class_start = cls_lineno
        class_end = cls_lineno + len(cls_lines) - 1
    except (OSError, TypeError):
        pass

    return {
        "name": name,
        "category": category,
        "path": source_path,
        "code": code,
        "class_start": class_start,
        "class_end": class_end,
    }


@router.put("/modules/{category}/{name}/code")
async def save_module_code(
    request: Request, category: str, name: str, body: ModuleCodeBody,
):
    """Overwrite the source file backing a registered module.

    Writes to the same path returned by ``GET /modules/.../code``. Changes
    take effect on the next server restart (modules are imported once at
    startup). Returns the resolved path and byte count written.
    """
    registry = _registry(request)
    try:
        cls = registry.get_module_class(category, name)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

    try:
        source_path = inspect.getsourcefile(cls)
    except TypeError:
        source_path = None
    if not source_path:
        raise HTTPException(
            status_code=404,
            detail=f"No source file for module '{name}' (likely defined dynamically)",
        )

    target = Path(source_path)
    try:
        target.write_text(body.code)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Cannot write source: {e}")

    return {
        "saved": True,
        "name": name,
        "category": category,
        "path": str(target),
        "bytes": len(body.code.encode("utf-8")),
        "restart_required": True,
    }


@router.post("/modules/{category}/{name}/reload")
async def reload_module(request: Request, category: str, name: str):
    """Re-import the Python module backing a registered plugin.

    Decorators in the file (e.g. ``@feature_extractor("bert")``) overwrite
    the registry entry on import, so on success the new class object
    replaces the old one for any subsequent lookup. In-flight runs and
    direct imports elsewhere keep their old reference; this is mostly
    fine because analysis pipelines look modules up through the registry.

    On a syntax / import error, the old class stays registered and we
    return a 422 with the traceback so the UI can surface it.
    """
    registry = _registry(request)
    try:
        cls = registry.get_module_class(category, name)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

    mod = inspect.getmodule(cls)
    if mod is None or not getattr(mod, "__name__", None):
        raise HTTPException(
            status_code=422,
            detail="Cannot determine the Python module to reload",
        )

    try:
        importlib.reload(mod)
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail={
                "message": f"{type(e).__name__}: {e}",
                "traceback": traceback.format_exc(),
                "module": mod.__name__,
            },
        )

    new_cls = registry.get_module_class(category, name)
    return {
        "reloaded": True,
        "module": mod.__name__,
        "replaced": id(new_cls) != id(cls),
    }


@router.get("/stages")
async def list_stages():
    """Return pipeline stage definitions across all scopes.

    The frontend ModuleBrowser groups by ``scope`` ("subject" / "group"
    / "study") to render one tab per scope. ``index`` restarts at 1
    per scope so each tab reads as its own ordered chain.
    """
    out: list[dict] = []
    for scope_name, scope_stages in (
        ('subject', list(ALL_STAGES)),
        ('group', GROUP_STAGES),
        ('study', STUDY_STAGES),
    ):
        for i, stage in enumerate(scope_stages):
            out.append({
                'name': stage,
                'scope': scope_name,
                'index': i + 1,
                'description': STAGE_DESCRIPTIONS.get(stage, ''),
                'module_categories': STAGE_MODULE_CATEGORIES.get(stage, []),
                'color': STAGE_COLORS.get(stage, '#ffffff'),
            })
    return out
