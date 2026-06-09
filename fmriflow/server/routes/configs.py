"""Experiment config browsing endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from fmriflow.core import paths

router = APIRouter(tags=["configs"])


def _count_group_runs(group_name: str) -> int:
    """Number of timestamped run dirs under ``group_runs/<group_name>/`` with a
    ``group_summary.json``. Legacy (no-run_id) layout counts as 1 if its
    summary file exists directly under the group dir."""
    if not group_name:
        return 0
    group_dir = paths.group_runs_root() / group_name
    if not group_dir.is_dir():
        return 0
    n = 0
    if (group_dir / "group_summary.json").is_file():
        n += 1
    for child in group_dir.iterdir():
        if not child.is_dir() or child.name == "latest":
            continue
        if (child / "group_summary.json").is_file():
            n += 1
    return n


def _count_study_runs(study_name: str) -> int:
    """Number of timestamped run dirs under ``study_runs/<study_name>/`` with a
    ``study_summary.json``."""
    if not study_name:
        return 0
    study_dir = paths.study_runs_root() / study_name
    if not study_dir.is_dir():
        return 0
    n = 0
    for child in study_dir.iterdir():
        if not child.is_dir() or child.name == "latest":
            continue
        if (child / "study_summary.json").is_file():
            n += 1
    return n


class SaveConfigBody(BaseModel):
    yaml_string: str


class CopyConfigBody(BaseModel):
    new_filename: str


@router.get("/configs")
async def list_configs(request: Request):
    """List all experiment configs with metadata."""
    store = request.app.state.config_store
    configs = store.list_configs()

    # Also get run counts per experiment+subject from run_store
    run_store = request.app.state.run_store
    all_runs = run_store.list_runs(limit=1000)

    # Count runs per experiment+subject
    run_counts: dict[str, int] = {}
    for run in all_runs:
        key = f"{run['summary'].experiment}|{run['summary'].subject}"
        run_counts[key] = run_counts.get(key, 0) + 1

    result = []
    for cfg in configs:
        if cfg.kind == "study":
            # `cfg.experiment` was lifted from the YAML's top-level
            # `study:` field — the directory name under study_runs/.
            n_runs = _count_study_runs(cfg.experiment)
        elif cfg.kind == "group":
            # For group configs, `cfg.experiment` was lifted from the
            # YAML's top-level `group:` field, which is the directory
            # name under group_runs/.
            n_runs = _count_group_runs(cfg.experiment)
        else:
            key = f"{cfg.experiment}|{cfg.subject}"
            n_runs = run_counts.get(key, 0)
        result.append({
            'filename': cfg.filename,
            'path': cfg.path,
            'experiment': cfg.experiment,
            'subject': cfg.subject,
            'model_type': cfg.model_type,
            'features': cfg.features,
            'output_dir': cfg.output_dir,
            'group': cfg.group,
            'preparation_type': cfg.preparation_type,
            'stimulus_loader': cfg.stimulus_loader,
            'response_loader': cfg.response_loader,
            'n_runs': n_runs,
            'kind': cfg.kind,
            'group_subjects': cfg.group_subjects,
            'study_groups': cfg.study_groups,
        })

    return result


@router.get("/configs/field-values")
async def field_values(request: Request):
    """Return unique values per field path across all configs (for autocomplete)."""
    store = request.app.state.config_store
    return store.field_values()


@router.get("/configs/{filename}")
async def get_config(request: Request, filename: str):
    """Get full config + raw YAML for a single config file."""
    store = request.app.state.config_store
    result = store.get_config(filename)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Config '{filename}' not found")
    return result


@router.post("/configs/{filename}/validate")
async def validate_config_file(request: Request, filename: str):
    """Validate a config file."""
    store = request.app.state.config_store
    return store.validate_config(filename)


@router.put("/configs/{filename}")
async def save_config(request: Request, filename: str, body: SaveConfigBody):
    """Overwrite (or create) a config file with raw YAML content."""
    store = request.app.state.config_store
    result = store.save_config(filename, body.yaml_string)
    if not result['saved']:
        raise HTTPException(status_code=400, detail="; ".join(result['errors']))
    return result


@router.post("/configs/{filename}/copy")
async def copy_config(request: Request, filename: str, body: CopyConfigBody):
    """Duplicate an existing config under a new filename."""
    store = request.app.state.config_store
    result = store.copy_config(filename, body.new_filename)
    if not result['saved']:
        status = 409 if any('already exists' in e for e in result['errors']) else 400
        raise HTTPException(status_code=status, detail="; ".join(result['errors']))
    return {**result, 'filename': body.new_filename}
