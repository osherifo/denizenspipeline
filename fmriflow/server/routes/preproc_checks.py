"""Checkpoints from the UI: the metric catalog, the editable norms overlay,
and a try-it evaluation of a check against a finished run's node.

  GET  /preproc/checks/metrics            registered metric functions
  GET  /preproc/checks/norms              effective table (built-ins + overlay) + the raw overlay
  PUT  /preproc/checks/norms              replace the overlay ({norms: {step: {hard, soft}}})
  GET  /preproc/nodes/{name}/checks       a node class's built-in checks, as data
  POST /preproc/checks/evaluate           {check, run_id, node_id} -> a Checkpoint (not recorded)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(tags=["preproc-checks"])


class NormsBody(BaseModel):
    norms: dict[str, Any]


class EvaluateBody(BaseModel):
    check: dict[str, Any]
    run_id: str
    node_id: str
    sequence: str | None = None


@router.get("/preproc/checks/metrics")
async def list_metrics():
    from fmriflow.preproc.checkpoints import metric_catalog
    return {"metrics": metric_catalog()}


@router.get("/preproc/checks/norms")
async def get_norms():
    from fmriflow.preproc.norms import load_user_norms, norms_table, user_norms_path
    user = {step: {k: {m: [op, list(v) if isinstance(v, tuple) else v] for m, (op, v) in b.items()} for k, b in row.items() if b}
            for step, row in load_user_norms().items()}
    return {"rows": norms_table(), "user": user, "path": str(user_norms_path())}


@router.put("/preproc/checks/norms")
async def put_norms(body: NormsBody):
    from fmriflow.preproc.norms import norms_table, save_user_norms
    try:
        save_user_norms(body.norms)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"saved": True, "rows": norms_table()}


@router.get("/preproc/nodes/{name}/checks")
async def node_checks(request: Request, name: str):
    reg = request.app.state.node_registry
    try:
        cls = reg.cls(name)
    except KeyError:
        raise HTTPException(404, f"Unknown preproc node: {name!r}")
    return {"checks": [c.to_dict() for c in (getattr(cls, "CHECKS", []) or [])]}


@router.post("/preproc/checks/evaluate")
async def evaluate_check(request: Request, body: EvaluateBody):
    """Run one check against the files a finished run's node produced, and
    return the checkpoint without recording it — the "try it" button."""
    from fmriflow.preproc.checkpoints import Check, evaluate, resolve_artifact
    from fmriflow.server.routes.preproc_run_nodes import _record
    from fmriflow.server.services.qc_files import find_fs_subject_dir

    rec = _record(request, body.run_id, body.node_id)
    try:
        check = Check.from_dict(body.check)
    except (KeyError, ValueError) as e:
        raise HTTPException(400, str(e))
    outputs = rec.get("outputs") or {}
    context: dict[str, Any] = {"node_dir": rec.get("work_dir") or "", "subject": rec.get("subject") or ""}
    for port, value in outputs.items():
        context[port] = str(value[0] if isinstance(value, list) and value else value or "")
    if outputs.get("derivatives_dir"):
        context.setdefault("derivatives_dir", str(outputs["derivatives_dir"]))
    fs_root = outputs.get("fs_subjects_dir")
    fs = find_fs_subject_dir(fs_root, rec.get("subject") or "", outputs.get("derivatives_dir"))
    if fs is not None:
        context["fs_subject_dir"] = str(fs)
        context.setdefault("fs_subjects_dir", str(fs.parent))
    if rec.get("work_dir"):
        context.setdefault("work_dir", rec["work_dir"])
    artifact = resolve_artifact(check.artifact, context)
    if artifact is None:
        raise HTTPException(400, f"artifact template {check.artifact!r} has a placeholder this node cannot fill; known: {sorted(context)}")
    if not Path(artifact).exists():
        return {"artifact": str(artifact), "exists": False, "checkpoint": None, "context": context}
    cp = evaluate(check, Path(artifact), run_id=body.run_id, node=body.node_id, subject=rec.get("subject") or "", sequence=body.sequence)
    return {"artifact": str(artifact), "exists": True, "checkpoint": cp.to_dict(), "context": context}
