"""NodeRegistry — the one library every preprocessing node lives in.

A *node* is a class decorated with ``@preproc_node("<name>", kind=...)``.
Whatever it wraps — a pure-Python transform, fmriprep in a container, an
imported nipype workflow, a BIDS source — it is picked from this registry
by name and placed in a :class:`~fmriflow.preproc.graph.Pipeline`.

Node kinds and the one method each must implement:

- ``interface``      ``run(inputs, out_dir, params) -> outputs``  (plain Python;
                     wrapped into a nipype interface by the adapters)
- ``container_app``  ``build_interface(params, bindings) -> nipype Interface``
- ``composite``      ``build(config) -> nipype Workflow`` (+ optional
                     ``validate`` / ``to_manifest``, the old workflow contract)
- ``source``         ``run(...)`` with no input ports; emits files from BIDS,
                     a manifest or a derivatives dir.

Class-level metadata (all optional except ``name``): ``version``,
``description``, ``INPUTS``, ``OUTPUTS`` (dict of port specs, or a plain
list), ``PARAM_SCHEMA``, ``REQUIRED_PYTHON``, ``REQUIRED_TOOLS``,
``REQUIRED_ENV``, ``CONTAINER``, ``CHECKS``.

Discovery tiers (lowest precedence first):

1. **Built-in** — modules under ``fmriflow.preproc.nodes``.
2. **Pip-packaged** — entry points in ``fmriflow.preproc_nodes`` (the older
   ``fmriflow.preproc_workflows`` / ``fmriflow.preproc_transforms`` groups
   are still honoured).
3. **User** — ``.py`` files under ``$FMRIFLOW_HOME/addons/nodes/``, plus the
   older ``addons/workflows/`` and ``addons/transforms/`` dirs.

Higher tiers shadow lower ones on a name collision; shadows are kept so
the UI can warn. The mechanics (snapshot ``_NODES`` before and after each
tier's imports, infer the source of pre-existing registrations from
``__module__``) are lifted from the workflow registry this replaces.
"""

from __future__ import annotations

import importlib
import os
import importlib.util
import logging
import pkgutil
from dataclasses import dataclass, field
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any

from fmriflow.graph.ports import normalize_ports as _normalize_ports
from fmriflow.preproc.graph import NODE_KINDS
from fmriflow.preproc.preflight import PreflightResult, preflight

logger = logging.getLogger(__name__)

BUILT_IN_PACKAGE = "fmriflow.preproc.nodes"
ENTRY_POINT_GROUPS = (
    "fmriflow.preproc_nodes",
    "fmriflow.preproc_workflows",
    "fmriflow.preproc_transforms",
)
USER_MODULE_PREFIX = "_fmriflow_user_node_"
# Module prefixes the older registries used for user files; a class loaded
# under one of these is a user node too.
_LEGACY_USER_PREFIXES = ("_fmriflow_user_workflow_", "_fmriflow_user_transform_")
_LEGACY_BUILTIN_PACKAGES: tuple[str, ...] = ()
USER_ADDON_KINDS = ("nodes", "workflows", "transforms")

NodeSource = str  # "built-in" | "user" | "pip:<dist>" | "unknown"

PortSpec = dict[str, Any]   # {"kind": "file" | "nifti" | "dir" | "str" | ..., "required": bool}


# ── Registration table ─────────────────────────────────────────────

_NODES: dict[str, type] = {}


def _origin(cls: type) -> tuple[str, str]:
    """(module stem without user prefix, qualname) — same file loaded under
    two module names registers the same class twice; that is not a shadow."""
    mod = getattr(cls, "__module__", "") or ""
    for prefix in (USER_MODULE_PREFIX, *_LEGACY_USER_PREFIXES):
        if mod.startswith(prefix):
            mod = mod[len(prefix):]
            break
    return mod, getattr(cls, "__qualname__", "")


def preproc_node(name: str, *, kind: str = "interface"):
    """Decorator: register ``cls`` as the node called ``name``.

    Sets ``cls.NODE_KIND`` and, when the class does not declare one,
    ``cls.name``.
    """
    if kind not in NODE_KINDS:
        raise ValueError(f"unknown node kind {kind!r}; expected one of {NODE_KINDS}")

    def wrapper(cls: type) -> type:
        existing = _NODES.get(name)
        if existing is not None and existing is not cls and _origin(existing) != _origin(cls):
            logger.warning(
                "Re-registering preproc node %r (was %s.%s, now %s.%s)",
                name, existing.__module__, existing.__qualname__,
                cls.__module__, cls.__qualname__,
            )
        cls.NODE_KIND = kind
        if not getattr(cls, "name", None):
            cls.name = name
        _NODES[name] = cls
        return cls

    return wrapper


def registered_nodes() -> dict[str, type]:
    """Snapshot of the raw registration table (tests, introspection)."""
    return dict(_NODES)


# ── Ports ──────────────────────────────────────────────────────────

def normalize_ports(spec: Any, *, default_kind: str = "file") -> dict[str, PortSpec]:
    """Coerce ``INPUTS`` / ``OUTPUTS`` into ``{port: {"kind", "required"}}``.

    Accepts a dict of port specs, a list of port names, or ``None``.
    Preprocessing ports default to ``kind: "file"``.
    """
    return _normalize_ports(spec, default_kind=default_kind)


def node_ports(cls: type) -> tuple[dict[str, PortSpec], dict[str, PortSpec]]:
    return (
        normalize_ports(getattr(cls, "INPUTS", None)),
        normalize_ports(getattr(cls, "OUTPUTS", None)),
    )


def node_kind(cls: type) -> str:
    """The registered kind, or an inference from the class shape."""
    k = getattr(cls, "NODE_KIND", None)
    if k in NODE_KINDS:
        return k
    if callable(getattr(cls, "build_interface", None)):
        return "container_app"
    if callable(getattr(cls, "build", None)):
        return "composite"
    return "interface"


UI_KEYS = ("inner_dag", "checkpoints", "log", "report", "structural_qc", "summary", "label_map", "views")


def node_ui(cls: type, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """What the run UI may show for this node — derived from the contract,
    overridable by a ``UI`` class attribute, and adjusted per run by an
    optional ``ui_for_params(params)`` method when ``params`` are given (an
    app that ran in a functional-only mode has no structural QC to show).

    The pipeline layer never looks at this. The frontend keeps generic tabs
    for every node and adds one per capability that names an output port:

    - ``inner_dag``: the app streams an inner nipype log (``INNER_NIPYPE_LOG``)
    - ``checkpoints``: the node declares ``CHECKS``
    - ``log``: a container app writes ``<node dir>/stdout.log``
    - ``report``: name of an output port of kind ``html`` (a subject report)
    - ``structural_qc``: a ``dir`` port named ``fs_subjects_dir`` or with
      ``role: freesurfer`` (FreeSurfer surfaces + review)
    - ``summary``: the ``manifest`` port (or ``role: manifest``)
    - ``label_map``: family of friendly labels for inner nodes (``"fmriprep"``)
    - ``views``: opaque extra view ids for addon authors; unknown ids are ignored
    """
    _, outputs = node_ports(cls)

    def port_where(pred) -> str | None:
        return next((n for n, spec in outputs.items() if pred(n, spec)), None)

    derived: dict[str, Any] = {
        "inner_dag": bool(getattr(cls, "INNER_NIPYPE_LOG", False)),
        "checkpoints": bool(getattr(cls, "CHECKS", None)),
        "log": node_kind(cls) == "container_app",
        "report": port_where(lambda n, spec: spec.get("kind") == "html"),
        "structural_qc": port_where(
            lambda n, spec: spec.get("kind") == "dir" and (n == "fs_subjects_dir" or spec.get("role") == "freesurfer")
        ),
        "summary": port_where(lambda n, spec: n == "manifest" or spec.get("role") == "manifest"),
        "label_map": None,
        "views": [],
    }
    declared = dict(getattr(cls, "UI", None) or {})
    ui = {**derived, **{k: v for k, v in declared.items() if k in UI_KEYS}}
    hook = getattr(cls, "ui_for_params", None)
    if params is not None and callable(hook):
        try:
            per_run = hook(cls(), dict(params)) or {}
        except Exception:  # a UI hint must never break a run view
            per_run = {}
        ui.update({k: v for k, v in per_run.items() if k in UI_KEYS})
    return ui


# ── Public record ──────────────────────────────────────────────────

@dataclass(frozen=True)
class NodeInfo:
    """What the UI needs to list a node — read from class attributes only."""

    name: str
    kind: str
    version: str
    description: str
    source: NodeSource
    container_bound: bool
    inputs: dict[str, PortSpec] = field(default_factory=dict)
    outputs: dict[str, PortSpec] = field(default_factory=dict)
    required_python: list[str] = field(default_factory=list)
    required_tools: list[str] = field(default_factory=list)
    required_env: list[str] = field(default_factory=list)
    params_schema: dict = field(default_factory=dict)
    checks: list[str] = field(default_factory=list)
    ui: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "version": self.version,
            "description": self.description,
            "source": self.source,
            "container_bound": self.container_bound,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "required_python": self.required_python,
            "required_tools": self.required_tools,
            "required_env": self.required_env,
            "params_schema": self.params_schema,
            "checks": self.checks,
            "ui": self.ui,
        }


@dataclass(frozen=True)
class _Entry:
    cls: type
    source: NodeSource


def _infer_source(cls: type, pip_modules: dict[str, str]) -> NodeSource:
    mod = getattr(cls, "__module__", "") or ""
    if mod.startswith(BUILT_IN_PACKAGE) or any(mod.startswith(p) for p in _LEGACY_BUILTIN_PACKAGES):
        return "built-in"
    if mod.startswith(USER_MODULE_PREFIX) or any(mod.startswith(p) for p in _LEGACY_USER_PREFIXES):
        return "user"
    for prefix, source in pip_modules.items():
        if mod == prefix or mod.startswith(prefix + "."):
            return source
    return "unknown"


# ── Registry ───────────────────────────────────────────────────────

# Built-in nodes kept out of the library until they earn their place (no pipeline
# uses them). They still register and their tests still run; a registry built
# with ``include_parked=True`` (or ``FMRIFLOW_INCLUDE_PARKED_NODES=1``) lists them.
PARKED_NODE_NAMES: frozenset[str] = frozenset({
    "smooth", "regress_confounds", "physio_estimate", "manifest_source",
})


def _include_parked_default() -> bool:
    return os.environ.get("FMRIFLOW_INCLUDE_PARKED_NODES", "").strip().lower() in ("1", "true", "yes")


@dataclass
class NodeRegistry:
    """Discovers and serves the node library.

    ``user_dirs`` defaults to ``$FMRIFLOW_HOME/addons/{nodes,workflows,transforms}``;
    tests pass explicit paths to stay out of the developer's real home.
    ``include_parked`` keeps the built-ins in :data:`PARKED_NODE_NAMES` in the library.
    """

    user_dirs: list[Path] | None = None
    include_parked: bool | None = None
    _entries: dict[str, _Entry] = field(default_factory=dict)
    _shadowed: list[tuple[str, NodeSource]] = field(default_factory=list)
    _pip_modules: dict[str, str] = field(default_factory=dict)

    # ── discovery ─────────────────────────────────────────────────

    def discover(self) -> NodeRegistry:
        self._entries.clear()
        self._shadowed.clear()
        self._pip_modules.clear()
        self._discover_builtin()
        self._discover_entry_points()
        self._discover_user_dirs()
        keep = self.include_parked if self.include_parked is not None else _include_parked_default()
        if not keep:
            for name in list(self._entries):
                if name in PARKED_NODE_NAMES and self._entries[name].source == "built-in":
                    del self._entries[name]
        return self

    def _claim_diff(self, pre: dict[str, type], source: NodeSource) -> None:
        for name, cls in _NODES.items():
            prev_cls = pre.get(name)
            if prev_cls is cls:
                continue
            if prev_cls is not None and _origin(prev_cls) != _origin(cls):
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
                self._entries[name] = _Entry(cls=cls, source=_infer_source(cls, self._pip_modules))

    def _discover_builtin(self) -> None:
        pre = dict(_NODES)
        try:
            pkg = importlib.import_module(BUILT_IN_PACKAGE)
        except ImportError as e:
            logger.debug("Built-in nodes package not importable: %s", e)
            self._claim_pre_existing(pre)
            return
        for module_info in pkgutil.iter_modules(getattr(pkg, "__path__", []) or []):
            if module_info.name.startswith("_"):
                continue
            mod_name = f"{BUILT_IN_PACKAGE}.{module_info.name}"
            try:
                importlib.import_module(mod_name)
            except Exception as e:
                logger.exception("Built-in node module %s failed to import: %s", mod_name, e)
        self._claim_pre_existing(pre)
        self._claim_diff(pre, source="built-in")

    def _discover_entry_points(self) -> None:
        pre = dict(_NODES)
        for group in ENTRY_POINT_GROUPS:
            try:
                eps = importlib_metadata.entry_points(group=group)
            except TypeError:  # pragma: no cover — older importlib.metadata
                eps = importlib_metadata.entry_points().get(group, [])
            for ep in eps:
                try:
                    loaded = ep.load()
                except Exception as e:
                    logger.exception("Node entry point %s failed to load: %s", ep, e)
                    continue
                dist = getattr(ep, "dist", None)
                dist_name = (
                    dist.metadata["Name"]
                    if dist is not None and getattr(dist, "metadata", None) is not None
                    else "unknown"
                )
                mod_name = getattr(loaded, "__module__", None)
                if mod_name:
                    self._pip_modules[mod_name] = f"pip:{dist_name}"
        self._claim_diff(pre, source="pip:unknown")
        for name, entry in list(self._entries.items()):
            if entry.source.startswith("pip:"):
                refined = _infer_source(entry.cls, self._pip_modules)
                if refined.startswith("pip:") and refined != entry.source:
                    self._entries[name] = _Entry(cls=entry.cls, source=refined)

    def _resolved_user_dirs(self) -> list[Path]:
        if self.user_dirs is not None:
            return list(self.user_dirs)
        try:
            from fmriflow.core.paths import addons_dir
            return [addons_dir(kind) for kind in USER_ADDON_KINDS]  # type: ignore[arg-type]
        except Exception as e:
            logger.debug("Could not resolve user node dirs: %s", e)
            return []

    def _discover_user_dirs(self) -> None:
        pre = dict(_NODES)
        for user_dir in self._resolved_user_dirs():
            if not user_dir.is_dir():
                continue
            for py_file in sorted(user_dir.glob("*.py")):
                if py_file.name.startswith("_"):
                    continue
                load_user_module(py_file)
        self._claim_diff(pre, source="user")

    # ── lookup ────────────────────────────────────────────────────

    def names(self) -> list[str]:
        return sorted(self._entries)

    def has(self, name: str) -> bool:
        return name in self._entries

    def cls(self, name: str) -> type:
        if name not in self._entries:
            available = ", ".join(self.names()) or "(none)"
            raise KeyError(f"Unknown preproc node: {name!r}. Available: {available}")
        return self._entries[name].cls

    def get(self, name: str) -> Any:
        """Instantiate a node by name."""
        return self.cls(name)()

    def kind(self, name: str) -> str:
        return node_kind(self.cls(name))

    def ports(self, name: str) -> tuple[dict[str, PortSpec], dict[str, PortSpec]]:
        return node_ports(self.cls(name))

    def source(self, name: str) -> NodeSource:
        return self._entries[name].source

    def info(self, name: str) -> NodeInfo:
        entry = self._entries.get(name)
        if entry is None:
            raise KeyError(f"Unknown preproc node: {name!r}")
        cls = entry.cls
        inputs, outputs = node_ports(cls)
        return NodeInfo(
            name=getattr(cls, "name", name) or name,
            kind=node_kind(cls),
            version=str(getattr(cls, "version", "") or ""),
            description=str(getattr(cls, "description", "") or (cls.__doc__ or "").strip().splitlines()[0] if (cls.__doc__ or "").strip() else ""),
            source=entry.source,
            container_bound=bool(getattr(cls, "CONTAINER", None)),
            inputs=inputs,
            outputs=outputs,
            required_python=list(getattr(cls, "REQUIRED_PYTHON", []) or []),
            required_tools=list(getattr(cls, "REQUIRED_TOOLS", []) or []),
            required_env=list(getattr(cls, "REQUIRED_ENV", []) or []),
            params_schema=dict(getattr(cls, "PARAM_SCHEMA", {}) or {}),
            checks=[getattr(c, "step", str(c)) for c in (getattr(cls, "CHECKS", []) or [])],
            ui=node_ui(cls),
        )

    def list(self, kind: str | None = None) -> list[NodeInfo]:
        infos = [self.info(n) for n in self.names()]
        return [i for i in infos if kind is None or i.kind == kind]

    def shadowed(self) -> list[tuple[str, NodeSource]]:
        return list(self._shadowed)

    def preflight(self, name: str) -> PreflightResult:
        return preflight(self.cls(name))


def load_user_module(py_file: Path) -> Any | None:
    """Import one user ``.py`` node file under the user module prefix.

    Returns the module, or ``None`` when it failed to load (logged).
    """
    mod_name = f"{USER_MODULE_PREFIX}{py_file.stem}"
    try:
        spec = importlib.util.spec_from_file_location(mod_name, py_file)
        if spec is None or spec.loader is None:
            logger.warning("Could not build spec for %s", py_file)
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception as e:
        logger.exception("User node file %s failed to load: %s", py_file, e)
        return None
