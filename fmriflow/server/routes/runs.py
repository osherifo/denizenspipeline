"""Run management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(tags=["runs"])


class RunConfigBody(BaseModel):
    config: dict


class RunFromConfigBody(BaseModel):
    config_path: str
    overrides: dict | None = None


@router.get("/runs")
async def list_runs(
    request: Request,
    limit: int = 50,
    experiment: str | None = None,
    subject: str | None = None,
):
    """List historical pipeline runs."""
    store = request.app.state.run_store
    runs = store.list_runs(limit=limit, experiment=experiment, subject=subject)
    return [_summarize_run(r) for r in runs]


@router.get("/runs/{run_id}")
async def get_run(request: Request, run_id: str):
    """Get full detail for a single run."""
    store = request.app.state.run_store
    run = store.get_run(run_id)
    if run is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return _full_run(run)


@router.post("/runs")
async def start_run(request: Request, body: RunConfigBody):
    """Launch a new pipeline run."""
    manager = request.app.state.run_manager
    run_id = manager.start_run(body.config)
    return {"run_id": run_id, "status": "started"}


@router.post("/runs/from-config")
async def start_run_from_config(request: Request, body: RunFromConfigBody):
    """Launch a pipeline run from a YAML config file path."""
    from pathlib import Path
    config_path = Path(body.config_path)
    if not config_path.is_file():
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Config file not found: {body.config_path}")
    manager = request.app.state.run_manager
    run_id = manager.start_run_from_config(str(config_path.resolve()), body.overrides)
    return {"run_id": run_id, "status": "started"}


@router.get("/runs/{run_id}/status")
async def run_status(request: Request, run_id: str):
    """Get current status of a running pipeline."""
    manager = request.app.state.run_manager
    status = manager.get_status(run_id)
    if status is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Active run '{run_id}' not found")
    return status


def _summarize_run(run: dict) -> dict:
    """Build a summary dict from a RunStore entry."""
    summary = run['summary']
    stages_status = 'ok'
    for s in summary.stages:
        if s.status == 'failed':
            stages_status = 'failed'
            break
        if s.status == 'warning':
            stages_status = 'warning'

    # Extract mean score from config_snapshot if available
    mean_score = None
    for s in summary.stages:
        if s.name == 'model' and s.status == 'ok' and s.detail:
            import re
            m = re.search(r'mean=([0-9.]+)', s.detail)
            if m:
                mean_score = float(m.group(1))

    return {
        'run_id': run['run_id'],
        'output_dir': run['output_dir'],
        'experiment': summary.experiment,
        'subject': summary.subject,
        'started_at': summary.started_at,
        'finished_at': summary.finished_at,
        'total_elapsed_s': summary.total_elapsed_s,
        'status': stages_status,
        'mean_score': mean_score,
        'stages': [
            {
                'name': s.name,
                'status': s.status,
                'elapsed_s': s.elapsed_s,
                'detail': s.detail,
            }
            for s in summary.stages
        ],
    }


def _full_run(run: dict) -> dict:
    """Build a full detail dict from a RunStore entry."""
    base = _summarize_run(run)
    base['config_snapshot'] = run['summary'].config_snapshot

    # List artifacts
    from fmriflow.server.services.run_store import RunStore
    from pathlib import Path
    output_dir = Path(run['output_dir'])
    artifacts = {}
    if output_dir.is_dir():
        for f in sorted(output_dir.iterdir()):
            if f.is_file() and f.name not in ('run_summary.json', 'pipeline.log'):
                artifacts[f.name] = {
                    'name': f.name,
                    'path': str(f),
                    'size': f.stat().st_size,
                    'type': _artifact_type(f),
                }
    base['artifacts'] = artifacts

    # Include log tail if available
    log_path = output_dir / 'pipeline.log'
    if log_path.is_file():
        try:
            text = log_path.read_text()
            lines = text.strip().split('\n')
            base['log_tail'] = '\n'.join(lines[-100:])
        except Exception:
            base['log_tail'] = None
    else:
        base['log_tail'] = None

    return base


def _artifact_type(path) -> str:
    """Classify artifact by extension."""
    suffix = path.suffix.lower()
    if suffix in ('.png', '.jpg', '.jpeg', '.svg'):
        return 'image'
    if suffix == '.json':
        return 'json'
    if suffix in ('.hdf5', '.h5', '.hdf'):
        return 'hdf5'
    if suffix in ('.npz', '.npy'):
        return 'numpy'
    if suffix == '.html':
        return 'html'
    return 'file'
