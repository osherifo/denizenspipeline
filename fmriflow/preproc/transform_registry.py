"""TransformRegistry — discovers and serves registered Stage-N transforms.

Three discovery tiers (lowest precedence first):

1. **Built-in** — modules under ``fmriflow.preproc.builtin_transforms``.
2. **Pip-packaged** — entry points in the ``fmriflow.preproc_transforms``
   group.
3. **User** — Python files under ``$FMRIFLOW_HOME/addons/transforms/``.

Higher tiers shadow lower ones on name conflict. Shadows are
tracked so the UI can warn ("your 'smooth' override shadows the
built-in smooth").

Deliberately parallel to ``WorkflowRegistry`` rather than sharing
a base class. The contracts are different (workflows produce a
manifest from raw BIDS; transforms consume one and emit an updated
one), the discovery target packages differ, and the entry-point
groups differ. Keeping the two surfaces separate makes the
provenance — "is this a bootstrap workflow or a transform?" —
unambiguous at every call site, at the cost of ~150 lines of
near-duplicate registry plumbing.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import pkgutil
from dataclasses import dataclass, field
from importlib import metadata as importlib_metadata
from pathlib import Path

from fmriflow.preproc.transform import (
    Transform,
    TransformInfo,
    TransformSource,
)

logger = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "fmriflow.preproc_transforms"
BUILT_IN_PACKAGE = "fmriflow.preproc.builtin_transforms"
USER_MODULE_PREFIX = "_fmriflow_user_transform_"


# ── Module-level permanent registration table ─────────────────────

_REGISTRY: dict[str, type] = {}


def register_transform(name: str):
    """Decorator: register a class as a Stage-N transform.

    Usage:

        @register_transform("smooth")
        class SmoothTransform:
            name = "smooth"
            ...

    A single class may register as both a transform and a
    post-preproc DAG node (``@nipype_node``); the registries are
    independent.
    """

    def wrapper(cls: type) -> type:
        existing = _REGISTRY.get(name)
        if existing is not None and existing is not cls:
            logger.warning(
                "Re-registering transform %r (was %s.%s, now %s.%s)",
                name, existing.__module__, existing.__qualname__,
                cls.__module__, cls.__qualname__,
            )
        _REGISTRY[name] = cls
        # Also an interface node in the unified library.
        from fmriflow.preproc.node_registry import preproc_node
        preproc_node(name, kind="interface")(cls)
        return cls

    return wrapper


# ── Registry ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class _Entry:
    """Internal registry record: transform class + provenance."""

    cls: type
    source: TransformSource


def _infer_source(cls: type, pip_modules: dict[str, str]) -> TransformSource:
    """Best-effort source inference for pre-existing registrations.

    Used when a transform was imported (and thus registered) before
    ``discover()`` ran in this call.
    """
    mod = getattr(cls, "__module__", "") or ""
    # Built-in transforms now live in the unified node package.
    if mod.startswith(BUILT_IN_PACKAGE) or mod.startswith("fmriflow.preproc.nodes"):
        return "built-in"
    if mod.startswith(USER_MODULE_PREFIX):
        return "user"
    for prefix, source in pip_modules.items():
        if mod == prefix or mod.startswith(prefix + "."):
            return source
    return "unknown"


@dataclass
class TransformRegistry:
    """Discovers + serves registered transforms.

    ``user_dir`` defaults to ``$FMRIFLOW_HOME/addons/transforms/``
    via ``fmriflow.core.paths.addons_dir("transforms")``; tests
    pass an explicit path to isolate from the developer's home.
    """

    user_dir: Path | None = None
    _entries: dict[str, _Entry] = field(default_factory=dict)
    _shadowed: list[tuple[str, TransformSource]] = field(default_factory=list)
    _pip_modules: dict[str, str] = field(default_factory=dict)

    def discover(self) -> None:
        """Scan all three tiers and populate the registry."""
        self._entries.clear()
        self._shadowed.clear()
        self._pip_modules.clear()

        self._discover_builtin()
        self._discover_entry_points()
        self._discover_user_dir()

    def _claim_diff(self, pre: dict[str, type], source: TransformSource) -> None:
        for name, cls in _REGISTRY.items():
            prev_cls = pre.get(name)
            if prev_cls is cls:
                continue
            if prev_cls is not None:
                prev_entry = self._entries.get(name)
                prev_source = (
                    prev_entry.source if prev_entry is not None
                    else _infer_source(prev_cls, self._pip_modules)
                )
                self._shadowed.append((name, prev_source))
            self._entries[name] = _Entry(cls=cls, source=source)

    def _claim_pre_existing(self, pre: dict[str, type]) -> None:
        for name, cls in pre.items():
            if name not in self._entries:
                self._entries[name] = _Entry(
                    cls=cls,
                    source=_infer_source(cls, self._pip_modules),
                )

    def _discover_builtin(self) -> None:
        pre = dict(_REGISTRY)
        try:
            pkg = importlib.import_module(BUILT_IN_PACKAGE)
        except ImportError as e:
            logger.debug("Built-in transforms package not importable: %s", e)
            self._claim_pre_existing(pre)
            return

        pkg_path = getattr(pkg, "__path__", None)
        if pkg_path:
            for module_info in pkgutil.iter_modules(pkg_path):
                if module_info.name.startswith("_"):
                    continue
                mod_name = f"{BUILT_IN_PACKAGE}.{module_info.name}"
                try:
                    importlib.import_module(mod_name)
                except Exception as e:
                    logger.exception(
                        "Built-in transform module %s failed to import: %s", mod_name, e
                    )

        self._claim_pre_existing(pre)
        self._claim_diff(pre, source="built-in")

    def _discover_entry_points(self) -> None:
        pre = dict(_REGISTRY)
        try:
            eps = importlib_metadata.entry_points(group=ENTRY_POINT_GROUP)
        except TypeError:
            eps = importlib_metadata.entry_points().get(ENTRY_POINT_GROUP, [])

        for ep in eps:
            try:
                loaded = ep.load()
            except Exception as e:
                logger.exception("Pip transform entry point %s failed to load: %s", ep, e)
                continue
            dist = getattr(ep, "dist", None)
            dist_name = (
                dist.metadata["Name"]
                if dist is not None and getattr(dist, "metadata", None) is not None
                else "unknown"
            )
            source: TransformSource = f"pip:{dist_name}"
            mod_name = getattr(loaded, "__module__", None)
            if mod_name:
                self._pip_modules[mod_name] = source

        self._claim_diff(pre, source="pip:unknown")
        for name, entry in list(self._entries.items()):
            if entry.source.startswith("pip:"):
                refined = _infer_source(entry.cls, self._pip_modules)
                if refined.startswith("pip:") and refined != entry.source:
                    self._entries[name] = _Entry(cls=entry.cls, source=refined)

    def _discover_user_dir(self) -> None:
        user_dir = self.user_dir
        if user_dir is None:
            try:
                from fmriflow.core.paths import addons_dir
                user_dir = addons_dir("transforms")
            except Exception as e:
                logger.debug("Could not resolve user transforms dir: %s", e)
                return

        if not user_dir.is_dir():
            return

        pre = dict(_REGISTRY)
        for py_file in sorted(user_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            mod_name = f"{USER_MODULE_PREFIX}{py_file.stem}"
            try:
                spec = importlib.util.spec_from_file_location(mod_name, py_file)
                if spec is None or spec.loader is None:
                    logger.warning("Could not build spec for %s", py_file)
                    continue
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
            except Exception as e:
                logger.exception("User transform %s failed to load: %s", py_file, e)
                continue

        self._claim_diff(pre, source="user")

    # ── Public API ────────────────────────────────────────────────

    def names(self) -> list[str]:
        return sorted(self._entries)

    def get(self, name: str) -> Transform:
        if name not in self._entries:
            available = ", ".join(self.names()) or "(none)"
            raise KeyError(
                f"Unknown transform: '{name}'. Available: {available}"
            )
        return self._entries[name].cls()

    def info(self, name: str) -> TransformInfo:
        if name not in self._entries:
            raise KeyError(f"Unknown transform: '{name}'")
        entry = self._entries[name]
        cls = entry.cls
        return TransformInfo(
            name=getattr(cls, "name", name),
            version=getattr(cls, "version", ""),
            description=getattr(cls, "description", ""),
            source=entry.source,
            container_bound=bool(getattr(cls, "CONTAINER", None)),
            inputs=list(getattr(cls, "INPUTS", []) or []),
            outputs=list(getattr(cls, "OUTPUTS", []) or []),
            required_python=list(getattr(cls, "REQUIRED_PYTHON", []) or []),
            required_tools=list(getattr(cls, "REQUIRED_TOOLS", []) or []),
            required_env=list(getattr(cls, "REQUIRED_ENV", []) or []),
            params_schema=dict(getattr(cls, "PARAM_SCHEMA", {}) or {}),
        )

    def list(self) -> list[TransformInfo]:
        return [self.info(n) for n in self.names()]

    def shadowed(self) -> list[tuple[str, TransformSource]]:
        return list(self._shadowed)
