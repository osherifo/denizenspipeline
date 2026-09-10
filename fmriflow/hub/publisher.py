"""Publish a local artifact up to a writable source (git commit + push).

Locates the local file(s) for a kind+name, stages them into the source's
clone under ``kinds/<kind>/``, regenerates the manifest entry (hash+size),
commits, and pushes to a branch. The curated (community) tier is expected to
review via PR, so we push to a branch and return a compare/PR URL rather than
writing to the default branch.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from fmriflow.core import paths
from fmriflow.hub import manifest
from fmriflow.hub.manifest import KINDS_DIR


class PublishError(RuntimeError):
    pass


def _first(glob_dir: Path, *names: str) -> Path | None:
    for n in names:
        p = glob_dir / n
        if p.is_file():
            return p
    return None


def locate_local(kind: str, name: str, state) -> tuple[list[Path], dict]:
    """Return the local file(s) for kind+name and any metadata to record."""
    if kind == "error":
        for p in sorted(paths.errors_dir().glob("*.yaml")):
            if p.stem == name or p.stem.endswith(name):
                return [p], {}
        raise PublishError(f"no local error entry '{name}'")

    if kind == "analysis_config":
        detail = state.config_store.get_config(name)
        if not detail:
            raise PublishError(f"no local analysis config '{name}'")
        return [Path(detail["path"])], {}

    if kind == "workflow_config":
        detail = state.workflow_config_store.get_config(name)
        if not detail:
            raise PublishError(f"no local workflow config '{name}'")
        return [Path(detail["path"])], {}

    # Stage configs: one store each, all exposing get_config(filename).
    _STAGE_CONFIG_STORES = {
        "convert_config": ("convert_config_store", "convert"),
        "preproc_config": ("pipeline_store", "preproc"),
        "autoflatten_config": ("autoflatten_config_store", "autoflatten"),
    }
    if kind in _STAGE_CONFIG_STORES:
        store_attr, label = _STAGE_CONFIG_STORES[kind]
        store = getattr(state, store_attr, None)
        if store is None:
            raise PublishError(f"server has no {store_attr}")
        detail = store.get_config(name)
        if not detail:
            raise PublishError(f"no local {label} config '{name}'")
        return [Path(detail["path"])], {}

    if kind == "stack_preset":
        # Pipelines first (the current shape), then any not-yet-migrated preset.
        p = _first(paths.config_dir("preproc"), f"{name}.yaml", f"{name}.yml") \
            or _first(paths.addons_dir("pipelines"), f"{name}.yaml", f"{name}.yml")
        if not p:
            raise PublishError(f"no local pipeline '{name}'")
        return [p], {}

    if kind == "module":
        from fmriflow.server.services.module_loader import get_modules_dir
        p = get_modules_dir() / f"{name}.py"
        if not p.is_file():
            raise PublishError(f"no local user module '{name}' (only user-tier modules can be published)")
        category = None
        for cat, lst in state.registry.list_modules().items():
            if name in lst:
                category = cat
                break
        return [p], {"category": category}

    if kind == "heuristic":
        from fmriflow.convert.heuristics import _heuristics_dir
        hd = _heuristics_dir()
        py = _first(hd, f"{name}.py")
        if not py:
            raise PublishError(f"no local heuristic '{name}'")
        out = [py]
        side = _first(hd, f"{name}.yaml", f"{name}.yml")
        if side:
            out.append(side)
        return out, {}

    if kind in ("transform", "workflow"):
        p = _first(paths.addons_dir(kind + "s"), f"{name}.py")
        if not p:
            raise PublishError(f"no local {kind} '{name}'")
        return [p], {}

    raise PublishError(f"cannot publish kind '{kind}'")


def _stage(repo_dir: Path, kind: str, name: str, state, *,
           author: str = "", description: str = ""):
    """Copy a local artifact's file(s) into ``kinds/<kind>/`` and build its
    manifest entry (no commit)."""
    files, meta = locate_local(kind, name, state)
    kind_dir = repo_dir / KINDS_DIR / kind
    kind_dir.mkdir(parents=True, exist_ok=True)
    rel_files: list[str] = []
    for f in files:
        dest = kind_dir / f.name
        shutil.copy2(f, dest)
        rel_files.append(str(dest.relative_to(repo_dir)))
    return manifest.build_entry(repo_dir, kind, name, rel_files,
                                description=description, author=author, metadata=meta)


def _merge_manifest(repo_dir: Path, new_entries: list) -> None:
    """Replace matching entries and write the manifest once."""
    keys = {(e.kind, e.name) for e in new_entries}
    kept = [e for e in manifest.read_manifest(repo_dir) if (e.kind, e.name) not in keys]
    manifest.write_manifest(repo_dir, kept + new_entries)


def publish(source, repo_dir: Path, kind: str, name: str, state, *,
            backend, token: str | None, author: str = "",
            description: str = "") -> dict:
    """Stage kind+name into *repo_dir*, update the manifest, commit + push."""
    from fmriflow.hub.template import ensure_scaffold
    ensure_scaffold(repo_dir)
    entry = _stage(repo_dir, kind, name, state, author=author, description=description)
    _merge_manifest(repo_dir, [entry])
    result = backend.publish(source.url, source.branch, repo_dir, token,
                             push_branch=f"hub/{kind}-{name}",
                             message=f"hub: add {kind}/{name}")
    result.update({"kind": kind, "name": name, "count": 1})
    return result


def publish_many(source, repo_dir: Path, kind: str, names: list[str], state, *,
                 backend, token: str | None, author: str = "") -> dict:
    """Publish every named artifact of one *kind* in a single commit/push."""
    from fmriflow.hub.template import ensure_scaffold
    ensure_scaffold(repo_dir)
    entries = [_stage(repo_dir, kind, n, state, author=author) for n in names]
    _merge_manifest(repo_dir, entries)
    result = backend.publish(source.url, source.branch, repo_dir, token,
                             push_branch=f"hub/{kind}-all",
                             message=f"hub: add {len(entries)} {kind} artifact(s)")
    result.update({"kind": kind, "count": len(entries), "names": names})
    return result
