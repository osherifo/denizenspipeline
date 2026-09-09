"""Adapters that turn registry node classes into nipype building blocks.

The node library holds three shapes of class (see
:mod:`fmriflow.preproc.node_registry`); nipype needs interfaces and
workflows. This module is the only place that knows both vocabularies:

- ``interface`` / ``source`` nodes write a plain ``run(inputs, out_dir,
  params) -> outputs``; :func:`make_interface` wraps that in
  :class:`RunNodeInterface`, whose input traits are the node's ports plus a
  ``params`` dict — so nipype's own
  hashing invalidates a node when a file or a parameter changes.
- ``container_app`` nodes build their own interface
  (``build_interface(params, bindings)``); :func:`make_container_interface`
  just calls it.
- ``composite`` nodes build a nipype ``Workflow``; :func:`build_composite`
  calls ``build`` and :func:`composite_ports` reads its ``inputnode`` /
  ``outputnode`` so the runner can wire edges by port name.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from nipype.interfaces.base import (
    BaseInterface,
    BaseInterfaceInputSpec,
    Directory,
    DynamicTraitedSpec,
    File,
    InputMultiPath,
    TraitedSpec,
    isdefined,
    traits,
)

from fmriflow.preproc.node_registry import node_kind, node_ports

logger = logging.getLogger(__name__)

FILE_KINDS = frozenset({
    "file", "nifti", "mgz", "gifti", "tsv", "csv", "json", "html", "image", "text",
})
DIR_KINDS = frozenset({"dir", "directory", "bids", "derivatives", "subjects_dir"})


def is_file_kind(kind: str) -> bool:
    return kind in FILE_KINDS


def is_dir_kind(kind: str) -> bool:
    return kind in DIR_KINDS


# ── run() nodes -> BaseInterface ──────────────────────────────────

def _input_trait(port: str, spec: dict[str, Any]):
    kind = str(spec.get("kind", "file"))
    desc = str(spec.get("description", "") or port)
    mandatory = bool(spec.get("required", False))
    if kind in FILE_KINDS:
        # InputMultiPath accepts one path or a list — so a MapNode's list
        # output can feed a plain node, and a single file is unwrapped.
        return InputMultiPath(File(exists=True), mandatory=mandatory, desc=desc)
    if kind in DIR_KINDS:
        return Directory(exists=True, mandatory=mandatory, desc=desc)
    return traits.Any(mandatory=mandatory, desc=desc)


def _to_path_value(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        items = [Path(v) if isinstance(v, str) else v for v in value]
        return items[0] if len(items) == 1 else items
    if isinstance(value, str):
        return Path(value)
    return value


def _from_path_value(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [str(v) if isinstance(v, Path) else v for v in value]
    return value


def _resolve_node_cls(node_type: str) -> type:
    from fmriflow.preproc.node_registry import registered_nodes
    cls = registered_nodes().get(node_type)
    if cls is None:
        raise KeyError(f"preproc node {node_type!r} is not registered in this process")
    return cls


class RunNodeInputSpec(DynamicTraitedSpec, BaseInterfaceInputSpec):
    node_type = traits.Str(mandatory=True, desc="registry name of the node class")
    params = traits.Dict(usedefault=True, desc="node parameters")


class RunNodeInterface(BaseInterface):
    """nipype interface around a ``run()`` node.

    One importable class (nipype pickles nodes, so the class must be
    reachable by module path); the ports become traits per instance, the
    way nipype's own ``Function`` interface does it. The node class is
    resolved by registry name at run time, so a class loaded from a user
    addon file resolves in whichever process runs it.
    """

    input_spec = RunNodeInputSpec
    output_spec = DynamicTraitedSpec

    def __init__(self, node_type: str, node_cls: type | None = None, **inputs: Any) -> None:
        cls = node_cls or _resolve_node_cls(node_type)
        in_ports, out_ports = node_ports(cls)
        self._in_ports = tuple(in_ports)
        self._out_ports = tuple(out_ports)
        port_values = {k: inputs.pop(k) for k in list(inputs) if k in in_ports}
        super().__init__(node_type=node_type, **inputs)
        for port, spec in in_ports.items():
            self.inputs.add_trait(port, _input_trait(port, spec))
        for port, value in port_values.items():
            setattr(self.inputs, port, value)

    def _outputs(self):
        base = super()._outputs()
        for port in self._out_ports:
            base.add_trait(port, traits.Any(desc=port))
        return base

    def _run_interface(self, runtime):
        cls = _resolve_node_cls(self.inputs.node_type)
        inputs: dict[str, Any] = {}
        for port in self._in_ports:
            value = getattr(self.inputs, port)
            if isdefined(value) and value not in (None, [], ""):
                inputs[port] = _to_path_value(value)
        params = dict(self.inputs.params) if isdefined(self.inputs.params) else {}
        out_dir = Path(runtime.cwd)
        out_dir.mkdir(parents=True, exist_ok=True)
        results = cls().run(inputs, out_dir, params) or {}
        self._results = {k: _from_path_value(v) for k, v in results.items()}
        return runtime

    def _list_outputs(self):
        outputs = self._outputs().get()
        for port in self._out_ports:
            if port in getattr(self, "_results", {}):
                outputs[port] = self._results[port]
        return outputs


def make_interface(cls: type, params: dict[str, Any] | None = None, **inputs: Any) -> RunNodeInterface:
    """Instantiate the interface for a ``run()`` node class."""
    if not callable(getattr(cls, "run", None)):
        raise TypeError(f"{cls.__name__} has no run() method; not an interface node")
    name = getattr(cls, "name", None) or cls.__name__
    iface = RunNodeInterface(node_type=name, node_cls=cls, **inputs)
    if params is not None:
        iface.inputs.params = dict(params)
    return iface


# ── container_app nodes ───────────────────────────────────────────

def make_container_interface(cls: type, params: dict[str, Any], bindings: dict[str, Any]) -> Any:
    """Ask a ``container_app`` node for its interface."""
    build = getattr(cls, "build_interface", None)
    if not callable(build):
        raise TypeError(f"{cls.__name__} has no build_interface(); not a container_app node")
    return cls().build_interface(dict(params), dict(bindings))


# ── composite nodes ───────────────────────────────────────────────

def build_composite(cls: type, config: Any) -> Any | None:
    """Call a composite node's ``build(config)``; returns the Workflow or ``None``.

    ``None`` means "nothing to execute" (the identity contract); the
    runner then skips the node and still calls ``to_manifest`` if asked.
    """
    build = getattr(cls, "build", None)
    if not callable(build):
        raise TypeError(f"{cls.__name__} has no build(); not a composite node")
    instance = cls()
    validate = getattr(instance, "validate", None)
    if callable(validate):
        errors = list(validate(config) or [])
        if errors:
            raise ValueError(f"node {getattr(cls, 'name', cls.__name__)!r} rejected the config: " + "; ".join(errors))
    built = instance.build(config)
    if built is None:
        return None
    if not callable(getattr(built, "run", None)):
        raise TypeError(
            f"{cls.__name__}.build() returned {type(built).__name__}, not a nipype Workflow"
        )
    return built


def composite_ports(workflow: Any) -> tuple[list[str], list[str]]:
    """Port names a composite exposes: its ``inputnode`` / ``outputnode`` fields.

    A workflow without those conventional nodes exposes nothing, which is
    fine for a bootstrap-style composite that only emits a manifest.
    """
    def _fields(node_name: str) -> list[str]:
        node = None
        try:
            node = workflow.get_node(node_name)
        except Exception:
            node = None
        if node is None:
            return []
        try:
            return [f for f in node.inputs.copyable_trait_names() if not f.startswith("_")]
        except Exception:
            return []

    return _fields("inputnode"), _fields("outputnode")


def describe(cls: type) -> dict[str, Any]:
    """Small helper for logs and tests: kind + ports of a node class."""
    inputs, outputs = node_ports(cls)
    return {"kind": node_kind(cls), "inputs": sorted(inputs), "outputs": sorted(outputs)}
