"""API routes for DICOM-to-BIDS conversion management."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(tags=["convert"])


# ── Request models ───────────────────────────────────────────────────────

class CollectBody(BaseModel):
    bids_dir: str
    subject: str
    source_dir: str | None = None
    heuristic: str | None = None
    sessions: list[str] | None = None
    dataset_name: str | None = None


class RunBody(BaseModel):
    source_dir: str
    bids_dir: str
    subject: str
    heuristic: str
    sessions: list[str] | None = None
    dataset_name: str | None = None
    grouping: str | None = None
    minmeta: bool = False
    overwrite: bool = True
    validate_bids: bool = True


class ScanBody(BaseModel):
    source_dir: str


class RegisterHeuristicBody(BaseModel):
    path: str
    name: str | None = None
    scanner_pattern: str | None = None
    description: str | None = None


class SaveHeuristicBody(BaseModel):
    name: str
    code: str
    description: str | None = None
    scanner_pattern: str | None = None
    tasks: list[str] | None = None


class HeuristicTemplateBody(BaseModel):
    name: str = "my_study"


class BatchJobBody(BaseModel):
    subject: str
    source_dir: str
    session: str = ""
    dataset_name: str | None = None
    grouping: str | None = None
    minmeta: bool | None = None
    overwrite: bool | None = None
    validate_bids: bool | None = None


class BatchRunBody(BaseModel):
    heuristic: str
    bids_dir: str
    jobs: list[BatchJobBody]
    source_root: str = ""
    max_workers: int = 2
    dataset_name: str = ""
    grouping: str = ""
    minmeta: bool = False
    overwrite: bool = True
    validate_bids: bool = True


class BatchParseYamlBody(BaseModel):
    yaml_text: str


class SaveConfigBody(BaseModel):
    name: str
    config: dict
    description: str = ""


class SaveRunConfigBody(BaseModel):
    name: str = ""
    description: str = ""
    params: dict


class SaveBatchConfigBody(BaseModel):
    name: str = ""
    description: str = ""
    params: dict


# ── Endpoints ────────────────────────────────────────────────────────────

@router.get("/convert/heuristics")
async def list_heuristics(request: Request):
    """List registered heuristics with metadata."""
    mgr = request.app.state.convert_manager
    return {"heuristics": mgr.list_heuristics()}


@router.get("/convert/tools")
async def check_tools(request: Request):
    """Check availability of conversion tools."""
    mgr = request.app.state.convert_manager
    return {"tools": mgr.check_tools()}


@router.get("/convert/decision-table")
async def get_convert_decision_table(
    bids_dir: str, subject: str, session: str | None = None,
):
    """What the heuristic did with every DICOM series it saw.

    Reconstructed from the provenance heudiconv leaves under
    ``.heudiconv/<subject>/info/`` — so it works on any already-converted
    dataset without re-running anything. Series the heuristic did not claim
    are reported as dropped, which is usually correct and occasionally the
    whole problem.

    ``session`` is optional: heudiconv writes ``.heudiconv/<sub>/ses-<ses>/``
    for sessioned conversions, and a single-session study resolves without
    the caller naming the label.

    404 when the dataset carries no heudiconv provenance (converted by other
    means, or ``.heudiconv`` removed).
    """
    from pathlib import Path

    from fmriflow.convert.decision_table import (
        DecisionTableError,
        build_decision_table,
    )

    # `subject` is interpolated into a path, so it must be one component.
    # Guarding the input rather than the resolved path: a containment check
    # on the result is measured against the already-escaped directory.
    if (
        not subject
        or subject in (".", "..")
        or "/" in subject
        or "\\" in subject
        or "\x00" in subject
    ):
        raise HTTPException(
            status_code=400,
            detail=f"subject must be a single path component, got {subject!r}",
        )

    if session and ("/" in session or "\\" in session or session in (".", "..")):
        raise HTTPException(
            status_code=400,
            detail=f"session must be a single path component, got {session!r}",
        )

    root = Path(bids_dir).expanduser().resolve()
    if not root.is_dir():
        raise HTTPException(status_code=404, detail=f"No such BIDS directory: {root}")

    try:
        table = build_decision_table(root, subject, session)
    except DecisionTableError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return table.to_dict()


@router.get("/convert/coverage")
async def get_convert_coverage(bids_dir: str):
    """Subjects x BIDS keys, cell = number of outputs.

    Reads the two failure modes apart at a glance: a column empty for EVERY
    subject is a rule that never matched (a code bug), while a column empty
    for ONE subject is that subject missing something the others have (a data
    incident). ``never_matched`` names the former.
    """
    from pathlib import Path

    from fmriflow.convert.decision_table import build_coverage

    root = Path(bids_dir).expanduser().resolve()
    if not root.is_dir():
        raise HTTPException(status_code=404, detail=f"No such BIDS directory: {root}")
    return build_coverage(root)


@router.get("/convert/flow")
async def get_convert_flow(bids_dir: str):
    """Aggregated protocol -> datatype -> suffix counts, for a Sankey.

    Study-level only. At series granularity a Sankey is unreadable; the point
    of this one is making the dropped ribbon impossible to scroll past.
    """
    from pathlib import Path

    from fmriflow.convert.decision_table import build_flow

    root = Path(bids_dir).expanduser().resolve()
    if not root.is_dir():
        raise HTTPException(status_code=404, detail=f"No such BIDS directory: {root}")
    return build_flow(root)


@router.get("/convert/manifests")
async def list_manifests(request: Request):
    """List discovered convert manifests."""
    mgr = request.app.state.convert_manager
    return {"manifests": mgr.scan_manifests()}


@router.get("/convert/manifests/{subject}")
async def get_manifest(request: Request, subject: str):
    """Get full manifest details for a subject."""
    mgr = request.app.state.convert_manager
    result = mgr.get_manifest(subject)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No manifest for subject '{subject}'")
    return result


@router.post("/convert/manifests/{subject}/validate")
async def validate_manifest(request: Request, subject: str):
    """Validate a convert manifest for a subject."""
    mgr = request.app.state.convert_manager
    return mgr.validate_manifest(subject)


@router.post("/convert/manifests/rescan")
async def rescan_manifests(request: Request):
    """Force rescan for convert manifests."""
    mgr = request.app.state.convert_manager
    mgr.invalidate_cache()
    return {"manifests": mgr.scan_manifests()}


@router.post("/convert/collect")
async def collect_bids(request: Request, body: CollectBody):
    """Build a manifest from an existing BIDS dataset."""
    mgr = request.app.state.convert_manager
    try:
        result = mgr.collect(body.model_dump(exclude_none=True))
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/convert/run")
async def start_run(request: Request, body: RunBody):
    """Start a heudiconv DICOM-to-BIDS conversion."""
    mgr = request.app.state.convert_manager
    try:
        run_id = mgr.start_run(body.model_dump(exclude_none=True))
        return {"run_id": run_id, "status": "started"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/convert/scan")
async def scan_dicom(request: Request, body: ScanBody):
    """Start a DICOM directory scan on a thread; poll ``GET /convert/scan/{scan_id}``.

    Scanning a large tree used to block the event loop for the whole server;
    now it runs in the background and can be cancelled.
    """
    mgr = request.app.state.convert_manager
    if not body.source_dir or not Path(body.source_dir).expanduser().is_dir():
        raise HTTPException(status_code=400, detail=f"not a directory: {body.source_dir}")
    scan_id = mgr.start_scan(body.source_dir)
    return mgr.get_scan(scan_id)


@router.get("/convert/scan/{scan_id}")
async def get_scan(request: Request, scan_id: str):
    job = request.app.state.convert_manager.get_scan(scan_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"unknown scan {scan_id!r}")
    return job


@router.post("/convert/scan/{scan_id}/cancel")
async def cancel_scan(request: Request, scan_id: str):
    return request.app.state.convert_manager.cancel_scan(scan_id)


@router.post("/convert/heuristics/register")
async def register_heuristic(request: Request, body: RegisterHeuristicBody):
    """Register a new heuristic file in the registry."""
    from fmriflow.convert.heuristics import register_heuristic as _register

    try:
        info = _register(
            path=body.path,
            name=body.name,
            scanner_pattern=body.scanner_pattern,
            description=body.description,
        )
        return {
            "name": info.name,
            "path": str(info.path),
            "description": info.description,
            "scanner_pattern": info.scanner_pattern,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/convert/heuristics/save")
async def save_heuristic(request: Request, body: SaveHeuristicBody):
    """Save heuristic code to disk (create or overwrite)."""
    from fmriflow.convert.heuristics import save_heuristic_code

    try:
        info = save_heuristic_code(body.name, body.code)

        # Update YAML sidecar metadata if provided
        if body.description or body.scanner_pattern or body.tasks:
            import yaml
            sidecar_path = info.path.with_suffix(".yaml")
            sidecar_data: dict = {}
            if sidecar_path.is_file():
                sidecar_data = yaml.safe_load(sidecar_path.read_text()) or {}
            sidecar_data["name"] = body.name
            if body.description is not None:
                sidecar_data["description"] = body.description
            if body.scanner_pattern is not None:
                sidecar_data["scanner_pattern"] = body.scanner_pattern
            if body.tasks is not None:
                sidecar_data["tasks"] = body.tasks
            sidecar_path.write_text(yaml.dump(sidecar_data, default_flow_style=False))

        return {
            "saved": True,
            "name": info.name,
            "path": str(info.path),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/convert/heuristics/template")
async def get_heuristic_template(request: Request, body: HeuristicTemplateBody):
    """Return the skeleton heudiconv template."""
    from fmriflow.convert.heuristics import get_heuristic_template as _template

    code = _template(name=body.name)
    return {"code": code, "name": body.name}


@router.delete("/convert/heuristics/{name}")
async def delete_heuristic(request: Request, name: str):
    """Remove a heuristic from the registry."""
    from fmriflow.convert.heuristics import remove_heuristic

    try:
        remove_heuristic(name)
        return {"deleted": True, "name": name}
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/convert/heuristics/{name}/code")
async def get_heuristic_code(request: Request, name: str):
    """Return the Python source code of a registered heuristic."""
    from fmriflow.convert.heuristics import read_heuristic_source

    try:
        code = read_heuristic_source(name)
        return {"name": name, "code": code}
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── Batch conversion ──────────────────────────────────────────────────────

@router.post("/convert/batch/run")
async def start_batch(request: Request, body: BatchRunBody):
    """Start a batch DICOM-to-BIDS conversion."""
    from fmriflow.convert.batch import BatchConfig, BatchJobConfig

    mgr = request.app.state.convert_manager
    try:
        batch_config = BatchConfig(
            heuristic=body.heuristic,
            bids_dir=body.bids_dir,
            jobs=[
                BatchJobConfig(
                    subject=j.subject,
                    source_dir=j.source_dir,
                    session=j.session,
                    dataset_name=j.dataset_name,
                    grouping=j.grouping,
                    minmeta=j.minmeta,
                    overwrite=j.overwrite,
                    validate_bids=j.validate_bids,
                )
                for j in body.jobs
            ],
            source_root=body.source_root,
            max_workers=body.max_workers,
            dataset_name=body.dataset_name,
            grouping=body.grouping,
            minmeta=body.minmeta,
            overwrite=body.overwrite,
            validate_bids=body.validate_bids,
        )
        batch_id = mgr.start_batch(batch_config)
        return {"batch_id": batch_id, "status": "started", "n_jobs": len(body.jobs)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/convert/batch/{batch_id}")
async def get_batch_status(request: Request, batch_id: str):
    """Get status summary for a batch conversion."""
    mgr = request.app.state.convert_manager
    result = mgr.get_batch_status(batch_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Batch '{batch_id}' not found")
    return result


@router.post("/convert/batch/{batch_id}/retry-failed")
async def retry_failed_batch(request: Request, batch_id: str):
    """Get the failed jobs from a batch for retry."""
    mgr = request.app.state.convert_manager
    try:
        result = mgr.retry_failed(batch_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/convert/batch/parse-yaml")
async def parse_batch_yaml(request: Request, body: BatchParseYamlBody):
    """Parse a YAML batch config and return as JSON."""
    from fmriflow.convert.batch import parse_batch_yaml as _parse

    try:
        config = _parse(body.yaml_text)
        return {
            "heuristic": config.heuristic,
            "bids_dir": config.bids_dir,
            "source_root": config.source_root,
            "max_workers": config.max_workers,
            "dataset_name": config.dataset_name,
            "grouping": config.grouping,
            "minmeta": config.minmeta,
            "overwrite": config.overwrite,
            "validate_bids": config.validate_bids,
            "jobs": [
                {
                    "subject": j.subject,
                    "source_dir": j.source_dir,
                    "session": j.session,
                }
                for j in config.jobs
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Saved configs ─────────────────────────────────────────────────────────

@router.get("/convert/configs")
async def list_saved_configs(request: Request):
    """List saved conversion configs."""
    store = request.app.state.convert_config_store
    return {"configs": store.list_configs()}


@router.get("/convert/configs/{filename}")
async def get_saved_config(request: Request, filename: str):
    """Get a saved conversion config."""
    store = request.app.state.convert_config_store
    result = store.get_config(filename)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Config '{filename}' not found")
    return result


@router.post("/convert/configs/save")
async def save_config(request: Request, body: SaveConfigBody):
    """Save a conversion config (raw dict)."""
    store = request.app.state.convert_config_store
    try:
        summary = store.save_config(body.name, body.config, body.description)
        return summary
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/convert/configs/save-run")
async def save_run_config(request: Request, body: SaveRunConfigBody):
    """Save a single-run conversion config from run params."""
    store = request.app.state.convert_config_store
    try:
        summary = store.save_from_run_params(body.params, body.name, body.description)
        return summary
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/convert/configs/save-batch")
async def save_batch_config(request: Request, body: SaveBatchConfigBody):
    """Save a batch conversion config from batch params."""
    store = request.app.state.convert_config_store
    try:
        summary = store.save_from_batch_params(body.params, body.name, body.description)
        return summary
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/convert/configs/{filename}")
async def delete_saved_config(request: Request, filename: str):
    """Delete a saved conversion config."""
    store = request.app.state.convert_config_store
    if not store.delete_config(filename):
        raise HTTPException(status_code=404, detail=f"Config '{filename}' not found")
    return {"deleted": True, "filename": filename}


@router.get("/convert/runs")
async def list_convert_runs(request: Request, include_finished: bool = True):
    """List active (and optionally finished) convert runs."""
    mgr = request.app.state.convert_manager
    return {"runs": mgr.list_runs(include_finished=include_finished)}


@router.get("/convert/runs/{run_id}")
async def get_convert_run(request: Request, run_id: str):
    """Return summary + last 200 log lines for one convert run."""
    mgr = request.app.state.convert_manager
    result = mgr.get_run(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return result


@router.post("/convert/runs/{run_id}/cancel")
async def cancel_convert_run(request: Request, run_id: str):
    """Cancel a running heudiconv subprocess (SIGTERM then SIGKILL)."""
    mgr = request.app.state.convert_manager
    result = mgr.cancel_run(run_id)
    if not result.get("cancelled"):
        raise HTTPException(status_code=409, detail=result.get("reason", "could not cancel"))
    return result


@router.delete("/convert/runs/{run_id}")
async def delete_convert_run(request: Request, run_id: str):
    """Delete a finished convert run: registry + sub-<subject>/ses-<ses>/ BIDS + .heudiconv cache."""
    mgr = request.app.state.convert_manager
    result = mgr.delete_run(run_id)
    if not result.get("deleted"):
        reason = result.get("reason", "could not delete")
        status = 409 if "running" in reason else 404
        raise HTTPException(status_code=status, detail=reason)
    return result


class RunFromConvertConfigBody(BaseModel):
    """Overrides shallow-merged on top of the YAML's config body."""
    subject: str | None = None
    source_dir: str | None = None
    bids_dir: str | None = None
    heuristic: str | None = None
    sessions: list[str] | None = None


@router.post("/convert/configs/{filename}/run")
async def run_saved_convert_config(
    request: Request,
    filename: str,
    body: RunFromConvertConfigBody | None = None,
):
    """Launch a single or batch conversion from a saved YAML config.

    Detects whether the file is a single-run or batch config and
    dispatches accordingly. Returns either ``{"kind": "single", "run_id": ...}``
    or ``{"kind": "batch", "batch_id": ...}``.
    """
    store = request.app.state.convert_config_store
    info = store.get_config(filename)
    if info is None:
        raise HTTPException(
            status_code=404,
            detail=f"Convert config '{filename}' not found",
        )

    mgr = request.app.state.convert_manager
    overrides = body.model_dump(exclude_none=True) if body else None
    try:
        result = mgr.start_run_from_config_file(
            info["path"], overrides=overrides,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {**result, "status": "started", "config": filename}
