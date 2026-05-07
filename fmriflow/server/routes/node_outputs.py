"""Per-nipype-node output endpoints.

Three routes, all rooted at ``/api/preproc/runs/{run_id}/node/{node_path:path}``:

- ``/files``  → list every artefact in the leaf's work_dir.
- ``/file?rel=…`` → serve a single artefact (suffix-whitelisted, safe-join).
- ``/pickle?rel=…`` → load a ``.pkl`` / ``.pklz`` and return a JSON
  rendering of its contents (best-effort, opt-in).

The leaf's work_dir is derived from the run's ``work_dir`` plus the
dotted node path (``a.b.c`` → ``a/b/c``).
"""

from __future__ import annotations

import gzip
import logging
import pickle
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

router = APIRouter(tags=["node-outputs"])
logger = logging.getLogger(__name__)

# Suffixes we serve via the GET /file endpoint. Mirrors the Structural-QC
# whitelist plus the formats fmriprep nodes commonly emit.
_NODE_OUTPUT_SUFFIXES = {
    ".nii", ".gz", ".mgz",
    ".json", ".tsv", ".dat", ".csv", ".txt", ".rst", ".log", ".cfg",
    ".svg", ".html", ".htm", ".png", ".jpg", ".jpeg", ".gif",
    ".pklz", ".pkl",
}

# Suffixes the frontend can render in-browser without help.
_VIEW_SUFFIXES = {
    ".nii", ".gz", ".mgz",
    ".json", ".tsv", ".csv", ".txt", ".rst", ".log", ".cfg",
    ".svg", ".html", ".htm", ".png", ".jpg", ".jpeg", ".gif",
}

# Pickled outputs are listed but go through the dedicated /pickle route.
_PICKLE_SUFFIXES = {".pklz", ".pkl"}

_MEDIA_TYPES = {
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".html": "text/html",
    ".htm": "text/html",
    ".json": "application/json",
    ".txt": "text/plain",
    ".log": "text/plain",
    ".cfg": "text/plain",
    ".rst": "text/plain",
    ".tsv": "text/tab-separated-values",
    ".csv": "text/csv",
    ".dat": "text/plain",
}


# ── helpers ─────────────────────────────────────────────────────────────


def _summary(request: Request, run_id: str) -> dict:
    mgr = request.app.state.preproc_manager
    s = mgr.get_run(run_id)
    if s is None:
        raise HTTPException(404, f"Run '{run_id}' not found")
    return s


def _node_dir(work_dir: str | None, node_path: str) -> Path:
    """Map a dotted node path to its work_dir leaf."""
    if not work_dir:
        raise HTTPException(409, "Run has no work_dir on record")
    parts = [p for p in node_path.split(".") if p]
    if not parts:
        raise HTTPException(400, "Empty node path")
    return Path(work_dir).joinpath(*parts)


def _safe_join(root: Path, rel: str) -> Path:
    """Resolve ``root / rel`` and refuse to leave ``root``."""
    target = (root / rel).resolve()
    root_resolved = root.resolve()
    sep = "/"
    if (
        not str(target).startswith(str(root_resolved) + sep)
        and target != root_resolved
    ):
        raise HTTPException(403, "Path escapes root")
    return target


def _kind_for(suffix: str, size: int) -> str:
    """Decide whether the frontend should render this inline or
    treat it as a link/special case."""
    if suffix in _PICKLE_SUFFIXES:
        return "pickle"
    if suffix in _VIEW_SUFFIXES:
        return "view"
    return "link"


# ── Pickle decoding ─────────────────────────────────────────────────────


def _open_pickle(path: Path):
    """Open a ``.pklz`` (gzip-wrapped) or ``.pkl`` for unpickling."""
    if path.suffix.lower() == ".pklz":
        return gzip.open(path, "rb")
    return path.open("rb")


def _to_jsonable(obj: Any, *, depth: int = 0, max_depth: int = 6) -> Any:
    """Best-effort JSON serialisation of arbitrary pickled objects.

    Renders dicts/lists/tuples/sets/scalars natively. Falls back to
    ``repr(obj)`` for anything else, keeping the output bounded.
    """
    if depth > max_depth:
        return f"…(max-depth {max_depth} reached)"
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, (bytes, bytearray)):
        return f"<bytes len={len(obj)}>"
    if isinstance(obj, dict):
        return {
            str(k): _to_jsonable(v, depth=depth + 1, max_depth=max_depth)
            for k, v in list(obj.items())[:200]
        }
    if isinstance(obj, (list, tuple)):
        return [
            _to_jsonable(v, depth=depth + 1, max_depth=max_depth)
            for v in list(obj)[:200]
        ]
    if isinstance(obj, set):
        return [
            _to_jsonable(v, depth=depth + 1, max_depth=max_depth)
            for v in list(obj)[:200]
        ]
    # Numpy arrays / nipype Bunch / arbitrary objects.
    try:
        import numpy as np  # type: ignore
        if isinstance(obj, np.ndarray):
            return {
                "__type__": "ndarray",
                "shape": list(obj.shape),
                "dtype": str(obj.dtype),
                "preview": obj.flatten().tolist()[:50] if obj.size else [],
            }
    except Exception:  # pragma: no cover — numpy isn't required
        pass
    # Try a __dict__ traversal for nipype-style result objects.
    if hasattr(obj, "__dict__"):
        d = vars(obj)
        if d:
            return {
                "__type__": type(obj).__name__,
                **{
                    str(k): _to_jsonable(v, depth=depth + 1, max_depth=max_depth)
                    for k, v in list(d.items())[:200]
                },
            }
    return repr(obj)[:1000]


# ── routes ──────────────────────────────────────────────────────────────


@router.get("/preproc/runs/{run_id}/work_tree")
async def list_work_tree(request: Request, run_id: str):
    """Walk the run's work_dir and return every nipype leaf directory
    discovered on disk.

    A leaf is any directory containing ``_node.pklz`` (nipype writes
    this for every executed node, cached or not) or ``result_*.pklz``.
    Returned paths are dotted (``a.b.c``) relative to ``work_dir``.
    """
    summary = _summary(request, run_id)
    work_dir = summary.get("work_dir")
    if not work_dir:
        return {"work_dir": None, "leaves": []}
    root = Path(work_dir)
    if not root.is_dir():
        return {"work_dir": str(root), "leaves": []}

    leaves: list[str] = []
    # Limit walk to fmriprep workflow roots to bound work.
    candidate_roots = [
        p for p in root.iterdir()
        if p.is_dir() and p.name.endswith("_wf")
    ] or [root]

    for wf_root in candidate_roots:
        for p in wf_root.rglob("_node.pklz"):
            leaf_dir = p.parent
            try:
                rel = leaf_dir.relative_to(root)
            except ValueError:
                continue
            # Skip report sub-dirs and meta dirs.
            parts = rel.parts
            if any(seg.startswith("_report") for seg in parts):
                continue
            leaves.append(".".join(parts))

    leaves = sorted(set(leaves))
    return {"work_dir": str(root), "leaves": leaves}


@router.get("/preproc/runs/{run_id}/node/{node_path:path}/files")
async def list_node_files(request: Request, run_id: str, node_path: str):
    """List artefacts in a node's work_dir."""
    summary = _summary(request, run_id)
    leaf = _node_dir(summary.get("work_dir"), node_path)
    if not leaf.is_dir():
        return {
            "node": node_path,
            "leaf_dir": str(leaf),
            "exists": False,
            "files": [],
            "crashes": [],
        }

    files: list[dict] = []
    for p in sorted(leaf.iterdir(), key=lambda x: x.name):
        if not p.is_file():
            continue
        suffix = p.suffix.lower()
        if suffix not in _NODE_OUTPUT_SUFFIXES:
            continue
        try:
            size = p.stat().st_size
        except OSError:
            continue
        files.append({
            "name": p.name,
            "rel": p.name,
            "suffix": suffix,
            "size": size,
            "kind": _kind_for(suffix, size),
        })

    # Pull any matching crash files for this leaf, regardless of timestamp.
    crashes: list[dict] = []
    output_dir = summary.get("output_dir")
    subject = summary.get("subject")
    if output_dir and subject:
        log_root = Path(output_dir) / f"sub-{subject}" / "log"
        if log_root.is_dir():
            leaf_name = node_path.rsplit(".", 1)[-1]
            for cp in sorted(log_root.rglob(f"crash-*-{leaf_name}-*.txt")):
                try:
                    crashes.append({"name": cp.name, "path": str(cp),
                                    "size": cp.stat().st_size})
                except OSError:
                    continue

    return {
        "node": node_path,
        "leaf_dir": str(leaf),
        "exists": True,
        "files": files,
        "crashes": crashes,
    }


@router.get("/preproc/runs/{run_id}/node/{node_path:path}/file")
async def get_node_file(
    request: Request, run_id: str, node_path: str, rel: str,
):
    """Serve a single file from a node's work_dir."""
    summary = _summary(request, run_id)
    leaf = _node_dir(summary.get("work_dir"), node_path)
    suffix = Path(rel).suffix.lower()
    if suffix not in _NODE_OUTPUT_SUFFIXES:
        raise HTTPException(403, f"Suffix not allowed: {suffix}")
    target = _safe_join(leaf, rel)
    if not target.is_file():
        raise HTTPException(404, f"File not found: {rel}")
    media_type = _MEDIA_TYPES.get(suffix, "application/octet-stream")
    return FileResponse(target, media_type=media_type)


@router.get("/preproc/runs/{run_id}/node/{node_path:path}/pickle")
async def get_node_pickle(
    request: Request, run_id: str, node_path: str, rel: str,
):
    """Load a pickled file under a node's work_dir, return a JSON
    rendering. Best-effort — unknown types fall back to ``repr``.
    """
    summary = _summary(request, run_id)
    leaf = _node_dir(summary.get("work_dir"), node_path)
    suffix = Path(rel).suffix.lower()
    if suffix not in _PICKLE_SUFFIXES:
        raise HTTPException(403, f"Not a pickle: {rel}")
    target = _safe_join(leaf, rel)
    if not target.is_file():
        raise HTTPException(404, f"File not found: {rel}")
    try:
        with _open_pickle(target) as f:
            obj = pickle.load(f)
    except Exception as e:
        return {"name": Path(rel).name, "error": f"{type(e).__name__}: {e}"}
    return {
        "name": Path(rel).name,
        "type": type(obj).__name__,
        "value": _to_jsonable(obj),
    }
