"""The analysis node catalog: every module and utility node as a node type.

Node type ids are ``<category>:<module>`` (``stimulus_loader:nsd`` and
``response_loader:nsd`` are different nodes), QA reporters are
``qa_reporter:<stage>.<name>``, and utility nodes are ``utility:<name>``.
The catalog answers the port-provider protocol of
:meth:`fmriflow.graph.GraphSpec.validate` (``has``, ``ports``, ``kind``).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from fmriflow.analysis.adapters import CATEGORY_ADAPTERS, Adapter, NativeAdapter, NodeEnv, is_native
from fmriflow.analysis.utility_nodes import UTILITY_NODES
from fmriflow.core.stages import GROUP_MODULE_STAGES, STUDY_MODULE_STAGES, SUBJECT_STAGES

# Classes defined by exec'd add-on files carry the loader's module name.
_ADDON_MODULES = frozenset({"fmriflow.modules.user_modules", "fmriflow.server.services.module_loader"})
_STAGE_ORDER = {s: i for i, s in enumerate((*SUBJECT_STAGES, *GROUP_MODULE_STAGES, *STUDY_MODULE_STAGES))}


def module_source(cls: type) -> str:
    mod = getattr(cls, "__module__", "") or ""
    if mod in _ADDON_MODULES or mod.startswith("_fmriflow_user"):
        return "addon"
    if mod.startswith("fmriflow."):
        return "builtin"
    return "package"


@dataclass
class AnalysisNodeInfo:
    type: str
    category: str
    module: str
    stage: str
    description: str
    full_description: str
    inputs: dict
    outputs: dict
    params_schema: dict
    error_policy: str
    source: str
    native: bool = False
    hidden: bool = False
    qa_stage: str | None = None
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class _Entry:
    adapter: Adapter
    module: str
    cls: type
    category: str
    qa_stage: str | None = None


class NodeCatalog:
    def __init__(self, registry: Any | None = None) -> None:
        self.registry = registry
        self._entries: dict[str, _Entry] = {}

    def discover(self) -> NodeCatalog:
        if self.registry is None:
            from fmriflow.registry import ModuleRegistry
            self.registry = ModuleRegistry()
            self.registry.discover()
        self._entries.clear()
        listed = self.registry.list_modules()
        for category, adapter in CATEGORY_ADAPTERS.items():
            if category == "qa_reporters":
                for stage, plugins in self.registry._qa_reporters.items():
                    for name, cls in plugins.items():
                        self._add(f"{adapter.prefix}:{stage}.{name}", adapter, name, cls, category, stage)
                continue
            for name in listed.get(category, []):
                cls = self.registry.get_module_class(category, name)
                self._add(f"{adapter.prefix}:{name}", adapter, name, cls, category)
        for util in UTILITY_NODES:
            name = util.NODE_TYPE.split(":", 1)[1]
            native = NativeAdapter(category="utility", prefix="utility", stage=util.STAGE).bind(util)
            self._entries[util.NODE_TYPE] = _Entry(native, name, util, "utility")
        return self

    def _add(self, type_id: str, adapter: Adapter, name: str, cls: type, category: str,
             qa_stage: str | None = None) -> None:
        if is_native(cls):
            adapter = NativeAdapter(category=category, prefix=adapter.prefix, stage=adapter.stage,
                                    error_policy=getattr(cls, "ERROR_POLICY", adapter.error_policy)).bind(cls)
        self._entries[type_id] = _Entry(adapter, name, cls, category, qa_stage)

    # ── port-provider protocol ───────────────────────────────────────

    def has(self, node_type: str) -> bool:
        return node_type in self._entries

    def _entry(self, node_type: str) -> _Entry:
        try:
            return self._entries[node_type]
        except KeyError:
            raise KeyError(f"unknown analysis node type {node_type!r}") from None

    def ports(self, node_type: str) -> tuple[dict, dict]:
        e = self._entry(node_type)
        return e.adapter.ports(e.cls, e.qa_stage)

    def node_ports(self, node: Any) -> tuple[dict, dict]:
        return self.ports(node.type)

    def kind(self, node_type: str) -> str:
        return self._entry(node_type).category

    # ── lookup ───────────────────────────────────────────────────────

    def names(self) -> list[str]:
        return sorted(self._entries)

    def adapter(self, node_type: str) -> Adapter:
        return self._entry(node_type).adapter

    def module_name(self, node_type: str) -> str:
        return self._entry(node_type).module

    def stage(self, node_type: str) -> str:
        e = self._entry(node_type)
        return e.qa_stage or e.adapter.stage

    def info(self, node_type: str) -> AnalysisNodeInfo:
        e = self._entry(node_type)
        doc = (e.cls.__doc__ or "").strip()
        ins, outs = e.adapter.ports(e.cls, e.qa_stage)
        return AnalysisNodeInfo(
            type=node_type,
            category=e.category,
            module=e.module,
            stage=self.stage(node_type),
            description=doc.split("\n")[0] if doc else "",
            full_description=doc,
            inputs=ins,
            outputs=outs,
            params_schema=e.adapter.params_schema(e.cls),
            error_policy=e.adapter.error_policy,
            source=module_source(e.cls),
            native=isinstance(e.adapter, NativeAdapter),
            hidden=e.module in e.adapter.HIDDEN,
            qa_stage=e.qa_stage,
        )

    def list(self, include_hidden: bool = False) -> list[AnalysisNodeInfo]:
        infos = [self.info(t) for t in self._entries]
        if not include_hidden:
            infos = [i for i in infos if not i.hidden]
        return sorted(infos, key=lambda i: (_STAGE_ORDER.get(i.stage, 99), i.category, i.type))

    # ── execution helpers ────────────────────────────────────────────

    def validate_node(self, node_type: str, params: dict, env: NodeEnv) -> list[str]:
        e = self._entry(node_type)
        return e.adapter.validate(e.module, params, env, e.qa_stage)

    def invoke(self, node_type: str, inputs: dict, params: dict, env: NodeEnv) -> dict[str, Any]:
        e = self._entry(node_type)
        return e.adapter.invoke(e.module, inputs, params, env, e.qa_stage)
