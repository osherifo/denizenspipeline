"""Module introspection endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request

from fmriflow.orchestrator import ALL_STAGES
from fmriflow.server.routes import _registry

router = APIRouter(tags=["modules"])

STAGE_DESCRIPTIONS = {
    'stimuli': 'Load stimulus timing data (TextGrids, TRFiles)',
    'responses': 'Load fMRI response data',
    'features': 'Extract or load features from stimuli',
    'prepare': 'Trim, normalize, concatenate, delay',
    'model': 'Fit voxelwise encoding model',
    'analyze': 'Postprocessing analysis (variance partition, weights, etc.)',
    'report': 'Generate output artifacts (flatmaps, metrics, etc.)',
}

STAGE_MODULE_CATEGORIES = {
    'stimuli': ['stimulus_loaders'],
    'responses': ['response_loaders', 'response_readers'],
    'features': ['feature_extractors', 'feature_sources'],
    'prepare': ['preparers', 'preparation_steps'],
    'model': ['models'],
    'analyze': ['analyzers'],
    'report': ['reporters'],
}

STAGE_COLORS = {
    'stimuli': '#00e5ff',
    'responses': '#e040fb',
    'features': '#ffd600',
    'prepare': '#00e676',
    'model': '#448aff',
    'analyze': '#ff1744',
    'report': '#ffffff',
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


@router.get("/stages")
async def list_stages():
    """Return pipeline stage definitions."""
    return [
        {
            'name': stage,
            'index': i + 1,
            'description': STAGE_DESCRIPTIONS.get(stage, ''),
            'module_categories': STAGE_MODULE_CATEGORIES.get(stage, []),
            'color': STAGE_COLORS.get(stage, '#ffffff'),
        }
        for i, stage in enumerate(ALL_STAGES)
    ]
