"""Pipelines: templates, saved pipelines (CRUD), validation and launch."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from fmriflow.preproc.graph import Pipeline, PipelineRunRequest
from fmriflow.preproc.templates import (
    concrete_path_warnings, delete_user_template, list_templates, load_template, save_user_template,
)

router = APIRouter(tags=["preproc-pipelines"])


class PipelineBody(BaseModel):
    pipeline: dict[str, Any]


class TemplateBody(BaseModel):
    name: str
    pipeline: dict[str, Any]


class RunBody(BaseModel):
    """Launch: a saved pipeline by name *or* an inline pipeline, plus the run request."""

    pipeline: dict[str, Any] | None = None
    pipeline_name: str | None = None
    subject: str
    output_dir: str
    bids_dir: str | None = None
    derivatives_dir: str | None = None
    work_dir: str | None = None
    dataset: str = "unknown"
    task: str | None = None
    sessions: list[str] = []
    inputs: dict[str, Any] = {}
    plugin: str = "Linear"
    n_procs: int | None = None
    use_cache: bool = True
    rerun_from: list[str] = []
    abort_on_bad: bool = False
    params_override: dict[str, dict[str, Any]] = {}

    def to_request(self) -> PipelineRunRequest:
        data = self.model_dump()
        data.pop("pipeline", None)
        data.pop("pipeline_name", None)
        return PipelineRunRequest.from_dict(data)


def _parse(data: dict[str, Any]) -> Pipeline:
    try:
        return Pipeline.from_dict(data)
    except Exception as e:
        raise HTTPException(400, detail=f"invalid pipeline: {e}")


@router.get("/preproc/pipelines")
async def list_pipelines(request: Request):
    store = request.app.state.pipeline_store
    return {
        "pipelines": [p.to_dict() for p in store.list_pipelines()],
        "legacy": store.list_legacy(),
        "root": str(store.root),
    }


@router.get("/preproc/pipelines/templates")
async def pipeline_templates():
    return {"templates": list_templates()}


@router.get("/preproc/pipelines/templates/{name}")
async def pipeline_template(name: str):
    try:
        return {"pipeline": load_template(name).to_dict()}
    except KeyError as e:
        raise HTTPException(404, detail=str(e))


@router.post("/preproc/pipelines/templates")
async def save_template(request: Request, body: TemplateBody):
    """*Save as template*: write the editor's pipeline to the user tier.

    The run panel (``run_defaults``) is dropped — a template is a starting
    point, not a dataset. ``warnings`` lists node values that hold a
    concrete path and so will not travel; ``errors`` is the validation
    result (saved regardless, like a pipeline).
    """
    pipeline = _parse(body.pipeline)
    errors = pipeline.validate(request.app.state.node_registry)
    warnings = concrete_path_warnings(pipeline)
    try:
        path = save_user_template(body.name, pipeline)
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
    return {"saved": True, "name": body.name, "tier": "user", "path": str(path),
            "warnings": warnings, "errors": errors}


@router.delete("/preproc/pipelines/templates/{name}")
async def delete_template(name: str):
    try:
        deleted = delete_user_template(name)
    except ValueError as e:
        raise HTTPException(403, detail=str(e))
    if not deleted:
        raise HTTPException(404, detail=f"no user template named {name!r}")
    return {"deleted": True}


@router.post("/preproc/pipelines/validate")
async def validate_pipeline(request: Request, body: PipelineBody):
    pipeline = _parse(body.pipeline)
    errors = pipeline.validate(request.app.state.node_registry)
    return {"ok": not errors, "errors": errors, "is_linear": pipeline.is_linear()}


@router.post("/preproc/pipelines/run")
async def run_pipeline(request: Request, body: RunBody):
    manager = request.app.state.preproc_run_manager
    if body.pipeline is not None:
        pipeline, name = _parse(body.pipeline), body.pipeline_name
    elif body.pipeline_name:
        try:
            pipeline, name = manager.pipeline_store.load(body.pipeline_name), body.pipeline_name
        except KeyError as e:
            raise HTTPException(404, detail=str(e))
        except ValueError as e:
            raise HTTPException(400, detail=str(e))
    else:
        raise HTTPException(400, detail="give either 'pipeline' or 'pipeline_name'")
    try:
        run_id = manager.start_run(pipeline, body.to_request(), pipeline_name=name)
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
    return {"run_id": run_id, "status": "running"}


@router.get("/preproc/pipelines/{name}")
async def get_pipeline(request: Request, name: str):
    store = request.app.state.pipeline_store
    try:
        return {"name": name, "pipeline": store.load(name).to_dict(), "path": str(store.root / f"{name}.yaml")}
    except KeyError as e:
        raise HTTPException(404, detail=str(e))
    except ValueError as e:
        raise HTTPException(400, detail=str(e))


@router.put("/preproc/pipelines/{name}")
async def save_pipeline(request: Request, name: str, body: PipelineBody):
    store = request.app.state.pipeline_store
    pipeline = _parse(body.pipeline)
    errors = pipeline.validate(request.app.state.node_registry)
    try:
        path = store.save(name, pipeline)
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
    return {"saved": True, "name": name, "path": str(path), "errors": errors}


@router.delete("/preproc/pipelines/{name}")
async def delete_pipeline(request: Request, name: str):
    store = request.app.state.pipeline_store
    try:
        deleted = store.delete(name)
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
    if not deleted:
        raise HTTPException(404, detail=f"no pipeline named {name!r}")
    return {"deleted": True}
