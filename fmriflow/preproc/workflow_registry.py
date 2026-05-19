"""WorkflowRegistry — discovers and serves registered nipype bootstrap workflows.

Three discovery tiers (lowest precedence first):

1. **Built-in** — modules under ``fmriflow.preproc.backends.nipype_workflows``.
   Imported on registry construction so their ``@register_preproc_workflow``
   decorators fire.
2. **Pip-packaged** — entry points in the ``fmriflow.preproc_workflows``
   group. Each entry point is imported (which triggers its decorator).
3. **User** — Python files under ``$FMRIFLOW_HOME/addons/workflows/``.
   Loaded via ``importlib.util.spec_from_file_location``.

Higher tiers shadow lower ones when names collide — a user dropin
with the same name as a built-in wins. The shadowed entry is kept
on the side as a warning so the UI can surface "you have a custom
'reference' workflow shadowing the built-in one."

The decorator writes to a single module-level ``_REGISTRY`` dict at
import time. ``WorkflowRegistry.discover()`` triggers each tier's
imports and snapshots ``_REGISTRY`` before and after to figure out
which tier claimed which name. This handles the case where a
workflow module was already imported elsewhere in the process (the
decorator only fires once per module load, so re-import is a no-op
— but the class is still in ``_REGISTRY`` and gets claimed via
``__module__``-based inference).
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import pkgutil
from dataclasses import dataclass, field
from importlib import metadata as importlib_metadata
from pathlib import Path

from fmriflow.preproc.preproc_workflow import (
    PreprocWorkflow,
    WorkflowInfo,
    WorkflowSource,
)

logger = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "fmriflow.preproc_workflows"
BUILT_IN_PACKAGE = "fmriflow.preproc.backends.nipype_workflows"
USER_MODULE_PREFIX = "_fmriflow_user_workflow_"


# ── Module-level permanent registration table ─────────────────────
#
# The decorator writes here once, at import time. WorkflowRegistry
# instances read from it during discover(). Never cleared by the
# registry — only by the test fixture that needs isolation.

_REGISTRY: dict[str, type] = {}


def register_preproc_workflow(name: str):
    """Decorator: register a class as a nipype bootstrap workflow.

    Usage:

        @register_preproc_workflow("reference")
        class ReferenceWorkflow:
            name = "reference"
            ...
    """

    def wrapper(cls: type) -> type:
        existing = _REGISTRY.get(name)
        if existing is not None and existing is not cls:
            logger.warning(
                "Re-registering workflow %r (was %s.%s, now %s.%s)",
                name, existing.__module__, existing.__qualname__,
                cls.__module__, cls.__qualname__,
            )
        _REGISTRY[name] = cls
        return cls

    return wrapper


# ── Registry ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class _Entry:
    """Internal registry record: workflow class + provenance."""

    cls: type
    source: WorkflowSource


def _infer_source(cls: type, pip_modules: dict[str, str]) -> WorkflowSource:
    """Best-effort source inference for pre-existing registrations.

    ``pip_modules`` maps module-path-prefix → ``"pip:<dist-name>"`` so
    pip-discovered classes are correctly tagged even when their import
    pre-dates ``discover()``.
    """
    mod = getattr(cls, "__module__", "") or ""
    if mod.startswith(BUILT_IN_PACKAGE):
        return "built-in"
    if mod.startswith(USER_MODULE_PREFIX):
        return "user"
    for prefix, source in pip_modules.items():
        if mod == prefix or mod.startswith(prefix + "."):
            return source
    return "unknown"


@dataclass
class WorkflowRegistry:
    """Discovers + serves registered workflows.

    ``user_dir`` defaults to ``$FMRIFLOW_HOME/addons/workflows/`` via
    ``fmriflow.core.paths.addons_dir("workflows")``; tests pass an
    explicit path to isolate from the developer's real home.
    """

    user_dir: Path | None = None
    _entries: dict[str, _Entry] = field(default_factory=dict)
    _shadowed: list[tuple[str, WorkflowSource]] = field(default_factory=list)
    _pip_modules: dict[str, str] = field(default_factory=dict)

    def discover(self) -> None:
        """Scan all three tiers and populate the registry.

        Order matters — earlier tiers are overwritten by later ones
        on name conflict, so we go built-in → pip → user (the
        documented precedence).
        """
        self._entries.clear()
        self._shadowed.clear()
        self._pip_modules.clear()

        self._discover_builtin()
        self._discover_entry_points()
        self._discover_user_dir()

    def _claim_diff(self, pre: dict[str, type], source: WorkflowSource) -> None:
        """Compare ``_REGISTRY`` against ``pre`` snapshot; record diffs.

        Any name whose class changed (new or replaced) is claimed by
        ``source``. Replacements are also tracked as shadows so the UI
        can warn.
        """
        for name, cls in _REGISTRY.items():
            prev_cls = pre.get(name)
            if prev_cls is cls:
                continue  # unchanged
            if prev_cls is not None:
                # This tier overwrote a prior entry — that's a shadow.
                prev_entry = self._entries.get(name)
                prev_source = (
                    prev_entry.source if prev_entry is not None
                    else _infer_source(prev_cls, self._pip_modules)
                )
                self._shadowed.append((name, prev_source))
            self._entries[name] = _Entry(cls=cls, source=source)

    def _discover_builtin(self) -> None:
        pre = dict(_REGISTRY)
        try:
            pkg = importlib.import_module(BUILT_IN_PACKAGE)
        except ImportError as e:
            logger.debug("Built-in workflows package not importable: %s", e)
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
                        "Built-in workflow module %s failed to import: %s", mod_name, e
                    )

        # Anything that was pre-existing but is a built-in by module path
        # also gets claimed (the decorator fired in some earlier import).
        self._claim_pre_existing(pre)
        self._claim_diff(pre, source="built-in")

    def _claim_pre_existing(self, pre: dict[str, type]) -> None:
        """Claim entries that already existed in ``_REGISTRY`` before any
        tier's discovery ran in this discover() call.

        Source is inferred from ``cls.__module__``. Without this step,
        previously-imported workflows (e.g. an ``import identity``
        somewhere in the test session) would never show up in
        ``self._entries`` because no tier "discovers" them — they were
        already there.
        """
        for name, cls in pre.items():
            if name not in self._entries:
                self._entries[name] = _Entry(
                    cls=cls,
                    source=_infer_source(cls, self._pip_modules),
                )

    def _discover_entry_points(self) -> None:
        pre = dict(_REGISTRY)
        try:
            eps = importlib_metadata.entry_points(group=ENTRY_POINT_GROUP)
        except TypeError:
            # Older importlib.metadata API
            eps = importlib_metadata.entry_points().get(ENTRY_POINT_GROUP, [])

        for ep in eps:
            try:
                loaded = ep.load()
            except Exception as e:
                logger.exception("Pip workflow entry point %s failed to load: %s", ep, e)
                continue
            # Track the module path so _infer_source can tag entries
            # imported in this tier as pip:<dist>.
            dist = getattr(ep, "dist", None)
            dist_name = (
                dist.metadata["Name"]
                if dist is not None and getattr(dist, "metadata", None) is not None
                else "unknown"
            )
            source: WorkflowSource = f"pip:{dist_name}"
            mod_name = getattr(loaded, "__module__", None)
            if mod_name:
                self._pip_modules[mod_name] = source

        self._claim_diff(pre, source="pip:unknown")
        # Refine sources for pip-loaded entries using the pip_modules map.
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
                user_dir = addons_dir("workflows")
            except Exception as e:
                logger.debug("Could not resolve user workflows dir: %s", e)
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
                logger.exception("User workflow %s failed to load: %s", py_file, e)
                continue

        self._claim_diff(pre, source="user")

    # ── Public API ────────────────────────────────────────────────

    def names(self) -> list[str]:
        return sorted(self._entries)

    def get(self, name: str) -> PreprocWorkflow:
        """Instantiate and return a workflow by name.

        Raises ``KeyError`` if the workflow isn't registered.
        """
        if name not in self._entries:
            available = ", ".join(self.names()) or "(none)"
            raise KeyError(
                f"Unknown preproc workflow: '{name}'. Available: {available}"
            )
        return self._entries[name].cls()

    def info(self, name: str) -> WorkflowInfo:
        """Return externally-visible metadata for a workflow.

        Reads class attributes only — does not instantiate the class.
        """
        if name not in self._entries:
            raise KeyError(f"Unknown preproc workflow: '{name}'")
        entry = self._entries[name]
        cls = entry.cls
        return WorkflowInfo(
            name=getattr(cls, "name", name),
            version=getattr(cls, "version", ""),
            description=getattr(cls, "description", ""),
            source=entry.source,
            container_bound=bool(getattr(cls, "CONTAINER", None)),
            required_python=list(getattr(cls, "REQUIRED_PYTHON", []) or []),
            required_tools=list(getattr(cls, "REQUIRED_TOOLS", []) or []),
            required_env=list(getattr(cls, "REQUIRED_ENV", []) or []),
        )

    def list(self) -> list[WorkflowInfo]:
        return [self.info(n) for n in self.names()]

    def shadowed(self) -> list[tuple[str, WorkflowSource]]:
        """Return entries that were shadowed during discovery, for UI
        warnings. Each tuple is ``(workflow_name, shadowed_source)``.
        """
        return list(self._shadowed)
