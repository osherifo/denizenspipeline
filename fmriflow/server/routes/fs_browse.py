"""Server-side directory browsing for path fields.

Paths in the UI are only useful if the *server* can open them — inside
Docker that is the container's view, not the host's. These endpoints list
directories as the server sees them, restricted to a few roots:

- ``$FMRIFLOW_DATA`` (default ``$FMRIFLOW_HOME/data``), and its usual
  subdirs (``dicoms``, ``bids``, ``derivatives``) as shortcuts;
- ``$FMRIFLOW_HOME``;
- any extra roots listed in ``$FMRIFLOW_BROWSE_ROOTS`` (``:``-separated),
  e.g. a read-only bind mount of a lab data share.

Nothing outside those roots is ever listed; typed paths remain free-form.
"""

from __future__ import annotations

import os
from pathlib import Path

import re

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from fmriflow.core import paths

router = APIRouter(tags=["fs"])

ENV_EXTRA_ROOTS = "FMRIFLOW_BROWSE_ROOTS"
MAX_ENTRIES = 2000


def browse_roots() -> list[dict]:
    """Ordered, de-duplicated roots the browser may show."""
    roots: list[dict] = []
    seen: set[str] = set()

    def add(label: str, p: Path, *, kind: str = "data") -> None:
        try:
            rp = p.expanduser().resolve()
        except OSError:
            return
        if not rp.is_dir() or str(rp) in seen:
            return
        seen.add(str(rp))
        roots.append({"label": label, "path": str(rp), "kind": kind})

    try:
        data = paths.data()
        for sub in ("dicoms", "bids", "derivatives"):
            if (data / sub).is_dir():
                add(sub, data / sub)
        add("data", data)
    except Exception:
        pass
    try:
        add("home", paths.home(), kind="home")
    except Exception:
        pass
    for raw in (os.environ.get(ENV_EXTRA_ROOTS) or "").split(":"):
        raw = raw.strip()
        if raw:
            add(Path(raw).name or raw, Path(raw), kind="extra")
    return roots


def _under(target: Path, root: Path) -> bool:
    return target == root or root in target.parents


def _allowed(target: Path) -> bool:
    """Under a root either lexically (a symlink placed inside a root counts —
    that is a deliberate choice by whoever manages the data dir) or once resolved."""
    lexical = Path(os.path.normpath(str(target.expanduser().absolute())))
    try:
        resolved = target.expanduser().resolve()
    except OSError:
        resolved = lexical
    for r in browse_roots():
        root = Path(r["path"])
        if _under(lexical, root) or _under(resolved, root):
            return True
    return False


def _resolve(path: str) -> Path:
    if not path:
        raise HTTPException(400, "path is required")
    target = Path(os.path.normpath(str(Path(path).expanduser().absolute())))
    if not _allowed(target):
        raise HTTPException(403, "path is outside the browsable roots")
    return target


@router.get("/fs/roots")
async def get_roots():
    return {"roots": browse_roots(), "extra_roots_env": ENV_EXTRA_ROOTS}


@router.get("/fs/list")
async def list_dir(path: str = Query(...), show_files: bool = Query(True)):
    """Entries of one directory, directories first, alphabetical."""
    target = _resolve(path)
    if not target.exists():
        raise HTTPException(404, f"no such directory: {target}")
    if not target.is_dir():
        raise HTTPException(400, f"not a directory: {target}")
    dirs: list[dict] = []
    files: list[dict] = []
    try:
        with os.scandir(target) as it:
            for entry in it:
                if entry.name.startswith("."):
                    continue
                try:
                    if entry.is_symlink() and not (target / entry.name).exists():
                        # Dangling here — typically a link to a host path that is not
                        # mounted into the container. Show it, say why it cannot open.
                        files.append({"name": entry.name, "path": str(target / entry.name), "is_dir": False,
                                      "size": 0, "dangling": True, "link_target": os.readlink(entry.path)})
                    elif entry.is_dir(follow_symlinks=True):
                        dirs.append({"name": entry.name, "path": str(target / entry.name), "is_dir": True,
                                     "is_symlink": entry.is_symlink()})
                    elif show_files:
                        st = entry.stat(follow_symlinks=True)
                        files.append({"name": entry.name, "path": str(target / entry.name), "is_dir": False, "size": st.st_size})
                except OSError:
                    continue
                if len(dirs) + len(files) >= MAX_ENTRIES:
                    break
    except PermissionError:
        raise HTTPException(403, f"permission denied: {target}")
    dirs.sort(key=lambda e: e["name"].lower())
    files.sort(key=lambda e: e["name"].lower())
    if not show_files:
        files = [f for f in files if f.get("dangling")]
    parent = str(target.parent) if _allowed(target.parent) else None
    return {"path": str(target), "parent": parent, "entries": dirs + files, "truncated": len(dirs) + len(files) >= MAX_ENTRIES}


class MkdirBody(BaseModel):
    parent: str
    name: str


_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@router.post("/fs/mkdir")
async def make_dir(body: MkdirBody):
    """Create one new directory under a browsable root (e.g. a fresh BIDS output dir)."""
    parent = _resolve(body.parent)
    if not parent.is_dir():
        raise HTTPException(400, f"not a directory: {parent}")
    if not _NAME_RE.match(body.name):
        raise HTTPException(400, "folder name: letters, digits, '.', '_' and '-' only")
    target = parent / body.name
    if target.exists():
        raise HTTPException(409, f"already exists: {target}")
    try:
        target.mkdir()
    except PermissionError:
        raise HTTPException(403, f"permission denied: {parent}")
    return {"created": True, "path": str(target)}


@router.get("/fs/exists")
async def path_exists(path: str = Query(...)):
    """Does the *server* see this path? (A typed host path may not exist inside the container.)"""
    try:
        p = Path(path).expanduser()
    except Exception:
        return {"path": path, "exists": False, "is_dir": False}
    return {"path": path, "exists": p.exists(), "is_dir": p.is_dir(), "resolved": str(p.resolve()) if p.exists() else None}
