"""Install an artifact from a synced source clone into the local user tier.

Each kind routes to the *existing* per-kind writer so installed artifacts are
indistinguishable from ones the user authored — and the pipeline's runtime
resolvers pick them up unchanged. sha256 is verified before anything is
written (fail closed on mismatch/unhashed).
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from fmriflow.core import paths
from fmriflow.hub import manifest
from fmriflow.hub.manifest import ArtifactEntry

logger = logging.getLogger(__name__)


class InstallError(RuntimeError):
    pass


def _copy(src: Path, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    shutil.copy2(src, dest)
    return dest


def install(entry: ArtifactEntry, repo_dir: Path, state, source=None) -> dict:
    """Verify + install one artifact. Returns a small result dict."""
    if not entry.files:
        raise InstallError("artifact has no files")
    if not manifest.verify(repo_dir, entry):
        raise InstallError(
            f"checksum verification failed for {entry.kind}/{entry.name} "
            "(the file may be corrupt, unhashed, or an unfetched LFS pointer)."
        )
    files = [repo_dir / f for f in entry.files]
    for p in files:
        if not p.is_file():
            raise InstallError(f"missing file in source: {p.name}")

    handler = _HANDLERS.get(entry.kind)
    if handler is None:
        raise InstallError(f"don't know how to install kind '{entry.kind}'")
    installed = handler(entry, files, state)
    # Record where it came from so the existing browsers can badge origin.
    if source is not None:
        try:
            from fmriflow.hub import provenance
            provenance.record(entry.kind, _prov_key(entry, installed),
                              source=source, artifact_name=entry.name,
                              sha256=entry.sha256)
        except Exception as e:  # noqa: BLE001 - provenance is best-effort
            logger.warning("Could not record provenance for %s/%s: %s",
                           entry.kind, entry.name, e)
    return {"installed": True, "kind": entry.kind, "name": entry.name, **installed}


def _prov_key(entry: ArtifactEntry, installed: dict) -> str:
    """The identifier the relevant browser uses to match this artifact.

    Mostly the manifest name; errors are keyed by the YAML ``id`` field
    (which the Error browser shows) rather than the file stem.
    """
    if entry.kind == "error":
        path = installed.get("path")
        if path:
            try:
                import yaml
                raw = yaml.safe_load(Path(path).read_text()) or {}
                if raw.get("id") is not None:
                    return str(raw["id"])
            except Exception:  # noqa: BLE001
                pass
    return entry.name


# ── per-kind handlers ──

def _install_error(entry, files, state) -> dict:
    dest = _copy(files[0], paths.errors_dir())
    _bust_errors_cache()
    return {"path": str(dest)}


def _install_analysis_config(entry, files, state) -> dict:
    text = files[0].read_text()
    res = state.config_store.save_config(files[0].name, text)
    return {"path": res.get("path", "")}


def _install_workflow_config(entry, files, state) -> dict:
    text = files[0].read_text()
    res = state.workflow_config_store.save_config(files[0].name, text)
    return {"path": res.get("path", "")}


def _install_stack_preset(entry, files, state) -> dict:
    # Presets are directory-scanned YAML — a plain copy is the install.
    dest = _copy(files[0], paths.addons_dir("pipelines"))
    return {"path": str(dest)}


def _install_module(entry, files, state) -> dict:
    from fmriflow.server.services import module_loader
    category = entry.metadata.get("category")
    if not category:
        raise InstallError("module artifact is missing metadata.category")
    code = files[0].read_text()
    path = module_loader.save_module(code, entry.name, category)
    try:
        module_loader.register_code(code)  # hot-register (no restart)
    except Exception as e:  # noqa: BLE001
        logger.warning("Installed module %s but hot-register failed: %s", entry.name, e)
    return {"path": str(path), "category": category}


def _install_heuristic(entry, files, state) -> dict:
    from fmriflow.convert import heuristics
    hdir = heuristics._heuristics_dir()
    hdir.mkdir(parents=True, exist_ok=True)
    dest = None
    for p in files:                       # .py and optional .yaml sidecar
        dest = _copy(p, hdir)
    return {"path": str(dest)}


def _install_code_addon(kind_dir: str, registry_attr: str):
    def handler(entry, files, state) -> dict:
        dest = _copy(files[0], paths.addons_dir(kind_dir))
        reg = getattr(state, registry_attr, None)
        if reg is not None:
            try:
                reg.discover()               # hot-register
            except Exception as e:  # noqa: BLE001
                logger.warning("Installed %s but rescan failed: %s", entry.name, e)
        return {"path": str(dest)}
    return handler


def _install_feature_array(entry, files, state) -> dict:
    dest_dir = paths.data() / "hub_features" / entry.name
    saved = [str(_copy(p, dest_dir)) for p in files]
    return {"paths": saved, "note": "reference these paths from an analysis config"}


_HANDLERS = {
    "error": _install_error,
    "analysis_config": _install_analysis_config,
    "workflow_config": _install_workflow_config,
    "stack_preset": _install_stack_preset,
    "module": _install_module,
    "heuristic": _install_heuristic,
    "transform": _install_code_addon("transforms", "transform_registry"),
    "workflow": _install_code_addon("workflows", "workflow_registry"),
    "feature_array": _install_feature_array,
}


def _bust_errors_cache() -> None:
    try:
        from fmriflow.server.routes import errors as _e
        _e._cache = None  # force a rescan on next list
    except Exception:  # noqa: BLE001
        pass


def local_names(kind: str, state) -> set[str]:
    """Names of this kind already present locally — for an 'installed' flag."""
    try:
        if kind == "error":
            # Catalog names error artifacts by file stem (NNNN_slug), so
            # match installed entries by stem, not the YAML `id` field.
            return {p.stem for p in paths.errors_dir().glob("*.yaml")}
        if kind == "analysis_config":
            return {c.filename for c in state.config_store.list_configs()}
        if kind == "workflow_config":
            return {c.filename for c in state.workflow_config_store.list_configs()}
        if kind == "module":
            names: set[str] = set()
            for lst in state.registry.list_modules().values():
                names.update(lst)
            return names
        if kind == "stack_preset":
            return {p.stem for p in paths.addons_dir("pipelines").glob("*.yaml")}
        if kind == "heuristic":
            from fmriflow.convert.heuristics import list_heuristics
            return {h.name for h in list_heuristics()}
        if kind in ("transform", "workflow"):
            return {p.stem for p in paths.addons_dir(kind + "s").glob("*.py")}
    except Exception:  # noqa: BLE001
        return set()
    return set()
