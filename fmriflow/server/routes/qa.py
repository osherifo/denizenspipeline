"""QA viz endpoints — list and regenerate per-stage diagnostic plots.

Each subject pipeline run can have a ``<run_dir>/qa/<stage>/<plugin>/``
tree populated either during the run (opt-in via ``qa.enabled: true``
in the config) or on demand from a saved
``<run_dir>/intermediates/<stage>.joblib`` intermediate.

The list endpoint is read-only and scans the filesystem. The
regenerate endpoint loads the intermediate, runs every registered
QA reporter for the stage, and rewrites the directory.

URL space mirrors the existing graph-viewer routes:

  GET  /api/runs/{run_id}/qa/{stage}                                — subject run
  POST /api/runs/{run_id}/qa/regenerate/{stage}                     — subject run
  GET  /api/group-runs/{name}/{run_id}/subject/{sub}/qa/{stage}     — group→subject
  POST /api/group-runs/{name}/{run_id}/subject/{sub}/qa/regenerate/{stage}
"""

from __future__ import annotations

import copy
import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from fmriflow import intermediates as _im
from fmriflow.context import PipelineContext
from fmriflow.core import paths

logger = logging.getLogger(__name__)
router = APIRouter(tags=["qa"])

# Stage names the QA layer recognises — mirrors ``intermediates.SAVEABLE_STAGES``.
_VALID_STAGES = set(_im.SAVEABLE_STAGES)


# ── helpers ────────────────────────────────────────────────────────────


def _check_path_segment(value: str, label: str) -> None:
    if not value or '/' in value or '..' in value or value.startswith('.'):
        raise HTTPException(
            status_code=400, detail=f"invalid {label}: {value!r}")


def _check_stage(stage: str) -> None:
    _check_path_segment(stage, "stage")
    if stage not in _VALID_STAGES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"unknown stage '{stage}'. "
                f"known: {sorted(_VALID_STAGES)}"
            ),
        )


def _registry(request: Request):
    reg = getattr(request.app.state, 'registry', None)
    if reg is None:
        from fmriflow.registry import ModuleRegistry
        reg = ModuleRegistry()
        reg.discover()
        request.app.state.registry = reg
    return reg


def _find_subject_run_dir(request: Request, run_id: str) -> Path:
    store = request.app.state.run_store
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(
            status_code=404, detail=f"Run '{run_id}' not found")
    out = run.get('output_dir')
    if not out:
        raise HTTPException(
            status_code=404, detail=f"Run '{run_id}' has no output_dir")
    return Path(out)


def _registered_plugins(stage: str) -> list[str]:
    """Names of QA reporters registered for ``stage`` (process-wide)."""
    from fmriflow.modules._decorators import _qa_reporters
    return sorted((_qa_reporters.get(stage) or {}).keys())


def _list_qa_artifacts(run_dir: Path | None, stage: str) -> dict:
    """Walk ``<run_dir>/qa/<stage>/`` and return a JSON summary.

    Tolerates a missing run dir (``run_dir=None`` or non-existent) so
    in-flight callers don't have to special-case "not yet on disk".
    The response always reports ``registered_plugins`` so the frontend
    can distinguish "no plugins for this stage in this build" from
    "QA hasn't been generated yet".
    """
    registered = _registered_plugins(stage)
    out: dict = {
        'stage': stage,
        'qa_dir': '',
        'plugins': [],
        'available': False,
        'registered_plugins': registered,
    }
    if run_dir is None or not run_dir.is_dir():
        return out
    qa_root = run_dir / 'qa' / stage
    out['qa_dir'] = str(qa_root)
    if not qa_root.is_dir():
        return out
    out['available'] = True
    for plugin_dir in sorted(qa_root.iterdir()):
        if not plugin_dir.is_dir():
            continue
        files = []
        for entry in sorted(plugin_dir.iterdir()):
            if not entry.is_file():
                continue
            try:
                size = entry.stat().st_size
            except OSError:
                size = 0
            files.append({
                'name': entry.name,
                'rel': str(entry.relative_to(run_dir)),
                'suffix': entry.suffix.lower(),
                'size': size,
            })
        if files:
            out['plugins'].append({'name': plugin_dir.name, 'files': files})
    return out


def _regenerate(run_dir: Path, stage: str, config: dict, registry) -> dict:
    """Reload the intermediate and re-run every registered QA reporter.

    Returns the same shape as :func:`_list_qa_artifacts`. Raises 404
    if no intermediate exists for this stage.
    """
    try:
        value = _im.load_intermediate(run_dir, stage)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=(
                f"no intermediate dump for stage '{stage}' under {run_dir}. "
                f"enable `intermediates.save: [{stage}, ...]` in the config "
                f"and re-run, OR fix the run to produce one."
            ),
        )
    # Force enabled + this single stage for the regenerate context. The
    # rest of the run's config (output_dir, etc.) carries through.
    qa_cfg = copy.deepcopy(config or {})
    qa_cfg.setdefault('reporting', {})['output_dir'] = str(run_dir)
    qa_cfg['qa'] = {
        'enabled': True,
        'stages': [stage],
        **(qa_cfg.get('qa') or {}),
    }
    qa_cfg['qa']['enabled'] = True
    qa_cfg['qa']['stages'] = [stage]
    ctx = PipelineContext(qa_cfg)
    ctx.run_stage_qa(stage, value, None)
    return _list_qa_artifacts(run_dir, stage)


def _serve_qa_file(run_dir: Path, rel: str) -> FileResponse:
    if not rel or rel.startswith('/'):
        raise HTTPException(status_code=400, detail="invalid file path")
    parts = rel.split('/')
    if any(p in ('', '..') or p.startswith('.') for p in parts):
        raise HTTPException(status_code=400, detail="invalid file path")
    full = (run_dir / rel).resolve(strict=False)
    base = run_dir.resolve(strict=False)
    if not str(full).startswith(str(base) + '/') and full != base:
        raise HTTPException(status_code=400, detail="path escapes run dir")
    if not full.is_file():
        raise HTTPException(status_code=404, detail=f"not a file: {rel}")
    return FileResponse(str(full))


def _resolve_group_subject_dir(
    request: Request, name: str, run_id: str, sub: str,
) -> Path:
    _check_path_segment(name, "group name")
    _check_path_segment(run_id, "run_id")
    _check_path_segment(sub, "subject")
    # Delegate to the registry-backed resolver so group runs whose
    # ``output_dir`` lives outside ``$FMRIFLOW_HOME`` still resolve —
    # the previous ``paths.group_runs_root() / ...`` hardcoded path
    # 404'd for those.
    from fmriflow.server.services.run_manager import resolve_group_run_dir
    registry = request.app.state.run_manager.registry
    run_dir = resolve_group_run_dir(registry, name, run_id)
    if run_dir is None:
        raise HTTPException(
            status_code=404,
            detail=f"group run not found: {name}/{run_id}")
    sub_dir = run_dir / 'subjects' / sub
    if not sub_dir.is_dir():
        raise HTTPException(
            status_code=404,
            detail=f"subject '{sub}' not in {name}/{run_id}")
    return sub_dir


def _resolve_in_flight_subject_run_dir(
    request: Request, run_id: str, *, strict: bool = True,
) -> tuple[Path | None, dict]:
    """For an active subject-scope run, return ``(run_dir, config)``.

    When ``strict=False``, returns ``(None, config)`` if the handle has
    no ``output_dir`` yet instead of raising — used by the list
    endpoint so polling pre-launch doesn't spew 404s.
    """
    rm = request.app.state.run_manager
    handle = rm.active_runs.get(run_id)
    if handle is None:
        raise HTTPException(
            status_code=404, detail=f"in-flight run '{run_id}' not found")
    if not handle.output_dir:
        if strict:
            raise HTTPException(
                status_code=404, detail=f"run '{run_id}' has no output_dir")
        return None, dict(handle.config or {})
    return Path(handle.output_dir), dict(handle.config or {})


def _resolve_in_flight_group_subject_dir(
    request: Request, run_id: str, sub: str, *, strict: bool = True,
) -> tuple[Path | None, dict]:
    """For an active group / study run, find the running subject's dir
    plus the resolved per-subject config (subject_template + override).

    The subject dir might not exist yet if the subject hasn't started.
    When ``strict=False``, returns ``(None, config)`` instead of 404
    so the list endpoint can return an empty result + keep the frontend
    from polling-with-noisy-404s.
    """
    _check_path_segment(sub, "subject")
    rm = request.app.state.run_manager
    handle = rm.active_runs.get(run_id)
    if handle is None:
        raise HTTPException(
            status_code=404, detail=f"in-flight run '{run_id}' not found")
    # Reuse the run-graph helpers (already battle-tested for the in-flight graph).
    from fmriflow.server.routes.run_graph import (
        _resolve_in_flight_subject_dir, _live_subject_config,
    )
    sub_dir = _resolve_in_flight_subject_dir(handle, sub)
    cfg = _live_subject_config(dict(handle.config or {}), sub)
    if sub_dir is None:
        if strict:
            raise HTTPException(
                status_code=404,
                detail=f"subject '{sub}' not yet on disk for in-flight run '{run_id}'",
            )
        return None, cfg
    return sub_dir, cfg


def _load_config_snapshot(run_dir: Path) -> dict:
    """Pull the config snapshot off the per-run summary JSON."""
    candidates = [run_dir / 'run_summary.json']
    for c in candidates:
        if c.is_file():
            try:
                data = json.loads(c.read_text())
                snap = data.get('config_snapshot') or {}
                if isinstance(snap, dict):
                    return snap
            except Exception:
                pass
    return {}


# ── subject runs ───────────────────────────────────────────────────────


@router.get("/runs/{run_id}/qa/{stage}")
async def subject_qa_list(request: Request, run_id: str, stage: str):
    _check_stage(stage)
    run_dir = _find_subject_run_dir(request, run_id)
    return _list_qa_artifacts(run_dir, stage)


@router.post("/runs/{run_id}/qa/regenerate/{stage}")
async def subject_qa_regenerate(request: Request, run_id: str, stage: str):
    _check_stage(stage)
    run_dir = _find_subject_run_dir(request, run_id)
    config = _load_config_snapshot(run_dir)
    return _regenerate(run_dir, stage, config, _registry(request))


@router.get("/runs/{run_id}/qa/{stage}/file/{rel:path}")
async def subject_qa_file(request: Request, run_id: str, stage: str, rel: str):
    _check_stage(stage)
    run_dir = _find_subject_run_dir(request, run_id)
    return _serve_qa_file(run_dir, rel)


# ── group runs → subject scope ─────────────────────────────────────────


@router.get("/group-runs/{name}/{run_id}/subject/{sub}/qa/{stage}")
async def group_subject_qa_list(
    request: Request, name: str, run_id: str, sub: str, stage: str,
):
    _check_stage(stage)
    run_dir = _resolve_group_subject_dir(request, name, run_id, sub)
    return _list_qa_artifacts(run_dir, stage)


@router.post("/group-runs/{name}/{run_id}/subject/{sub}/qa/regenerate/{stage}")
async def group_subject_qa_regenerate(
    request: Request, name: str, run_id: str, sub: str, stage: str,
):
    _check_stage(stage)
    run_dir = _resolve_group_subject_dir(request, name, run_id, sub)
    config = _load_config_snapshot(run_dir)
    return _regenerate(run_dir, stage, config, _registry(request))


@router.get("/group-runs/{name}/{run_id}/subject/{sub}/qa/{stage}/file/{rel:path}")
async def group_subject_qa_file(
    request: Request, name: str, run_id: str, sub: str, stage: str, rel: str,
):
    _check_stage(stage)
    run_dir = _resolve_group_subject_dir(request, name, run_id, sub)
    return _serve_qa_file(run_dir, rel)


# ── in-flight subject (live) ───────────────────────────────────────────


@router.get("/runs/in-flight/{run_id}/qa/{stage}")
async def in_flight_subject_qa_list(
    request: Request, run_id: str, stage: str,
):
    _check_stage(stage)
    run_dir, _ = _resolve_in_flight_subject_run_dir(
        request, run_id, strict=False,
    )
    return _list_qa_artifacts(run_dir, stage)


@router.post("/runs/in-flight/{run_id}/qa/regenerate/{stage}")
async def in_flight_subject_qa_regenerate(
    request: Request, run_id: str, stage: str,
):
    _check_stage(stage)
    run_dir, cfg = _resolve_in_flight_subject_run_dir(request, run_id)
    return _regenerate(run_dir, stage, cfg, _registry(request))


@router.get("/runs/in-flight/{run_id}/qa/{stage}/file/{rel:path}")
async def in_flight_subject_qa_file(
    request: Request, run_id: str, stage: str, rel: str,
):
    _check_stage(stage)
    run_dir, _ = _resolve_in_flight_subject_run_dir(request, run_id)
    return _serve_qa_file(run_dir, rel)


# ── in-flight group → subject (live) ───────────────────────────────────


@router.get("/runs/in-flight/{run_id}/subject/{sub}/qa/{stage}")
async def in_flight_group_subject_qa_list(
    request: Request, run_id: str, sub: str, stage: str,
):
    _check_stage(stage)
    run_dir, _ = _resolve_in_flight_group_subject_dir(
        request, run_id, sub, strict=False,
    )
    return _list_qa_artifacts(run_dir, stage)


@router.post("/runs/in-flight/{run_id}/subject/{sub}/qa/regenerate/{stage}")
async def in_flight_group_subject_qa_regenerate(
    request: Request, run_id: str, sub: str, stage: str,
):
    _check_stage(stage)
    run_dir, cfg = _resolve_in_flight_group_subject_dir(request, run_id, sub)
    return _regenerate(run_dir, stage, cfg, _registry(request))


@router.get("/runs/in-flight/{run_id}/subject/{sub}/qa/{stage}/file/{rel:path}")
async def in_flight_group_subject_qa_file(
    request: Request, run_id: str, sub: str, stage: str, rel: str,
):
    _check_stage(stage)
    run_dir, _ = _resolve_in_flight_group_subject_dir(request, run_id, sub)
    return _serve_qa_file(run_dir, rel)
