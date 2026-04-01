"""Config validation and conversion endpoints."""

from __future__ import annotations

import yaml
from fastapi import APIRouter, Request
from pydantic import BaseModel

from denizenspipeline.config.schema import validate_config
from denizenspipeline.plugins._schema import extract_schema, schema_defaults
from denizenspipeline.server.routes import _registry

router = APIRouter(tags=["config"])


class ConfigBody(BaseModel):
    config: dict


class PluginDefaultsBody(BaseModel):
    category: str
    plugin: str


@router.post("/config/validate")
async def validate(request: Request, body: ConfigBody):
    """Validate a pipeline config dict."""
    errors = validate_config(body.config)

    # Also run plugin-level validation
    registry = _registry(request)
    plugin_errors = _validate_plugins(registry, body.config)
    errors.extend(plugin_errors)

    return {"valid": len(errors) == 0, "errors": errors}


@router.post("/config/from-yaml")
async def from_yaml(request: Request):
    """Parse raw YAML into a config dict."""
    raw = (await request.body()).decode('utf-8')
    try:
        config = yaml.safe_load(raw)
        if not isinstance(config, dict):
            return {"config": {}, "errors": ["YAML did not produce a dict"]}
        return {"config": config, "errors": []}
    except yaml.YAMLError as e:
        return {"config": {}, "errors": [str(e)]}


@router.post("/config/to-yaml")
async def to_yaml(body: ConfigBody):
    """Serialize a config dict to YAML."""
    # Remove None values for cleaner output
    cleaned = _strip_none(body.config)
    output = yaml.dump(
        cleaned,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    )
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(output, media_type="text/plain")


@router.post("/config/defaults")
async def get_defaults(request: Request, body: PluginDefaultsBody):
    """Return default parameter values for a plugin."""
    registry = _registry(request)
    cls = registry.get_plugin_class(body.category, body.plugin)
    schema = extract_schema(cls)
    return {"params": schema_defaults(schema)}


def _validate_plugins(registry, config: dict) -> list[str]:
    """Run plugin-level validate_config where possible."""
    errors = []

    # Stimulus loader
    loader_name = config.get('stimulus', {}).get('loader', 'textgrid')
    try:
        loader = registry.get_stimulus_loader(loader_name)
        for e in loader.validate_config(config):
            errors.append(f"stimulus loader '{loader_name}': {e}")
    except Exception:
        pass

    # Response loader
    resp_name = config.get('response', {}).get('loader', 'cloud')
    try:
        loader = registry.get_response_loader(resp_name)
        for e in loader.validate_config(config):
            errors.append(f"response loader '{resp_name}': {e}")
    except Exception:
        pass

    # Model
    model_name = config.get('model', {}).get('type', 'bootstrap_ridge')
    try:
        model = registry.get_model(model_name)
        for e in model.validate_config(config):
            errors.append(f"model '{model_name}': {e}")
    except Exception:
        pass

    return errors


def _strip_none(d):
    """Recursively remove None values from a dict."""
    if isinstance(d, dict):
        return {k: _strip_none(v) for k, v in d.items() if v is not None}
    if isinstance(d, list):
        return [_strip_none(x) for x in d]
    return d
