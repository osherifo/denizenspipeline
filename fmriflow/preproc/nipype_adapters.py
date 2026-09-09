"""Adapters that turn registry node classes into nipype building blocks.

The node library holds three shapes of class (see
:mod:`fmriflow.preproc.node_registry`); nipype needs interfaces and
workflows. This module is the only place that knows both vocabularies:

- ``interface`` / ``source`` nodes write a plain ``run(inputs, out_dir,
  params) -> outputs``; :func:`make_interface` wraps that in
  :class:`RunNodeInterface`, whose input traits are the node's ports plus a
  ``params`` dict — so nipype's own
  hashing invalidates a node when a file or a parameter changes.
- ``container_app`` nodes supply ``build_command`` and ``collect``;
  :class:`ContainerAppInterface` runs the command in its own process group,
  logs it, and parses an inner nipype log when the node asks for it.
- ``composite`` nodes build a nipype ``Workflow``; :func:`build_composite`
  calls ``build`` and :func:`composite_ports` reads its ``inputnode`` /
  ``outputnode`` so the runner can wire edges by port name.
"""

from __future__ import annotations

import logging
import threading
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
    Undefined,
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
        # Output-style dirs (derivatives, work) are created by the node, so
        # existence is only enforced when the port spec asks for it.
        return Directory(exists=bool(spec.get("exists", False)), mandatory=mandatory, desc=desc)
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


def _add_output_ports(base: Any, ports: tuple[str, ...]) -> Any:
    """Add one ``Any`` trait per output port, initialised to ``Undefined``.

    nipype's MapNode collation starts each output as ``[]`` only when the
    fresh value is *undefined*; ``traits.Any`` defaults to ``None``, which
    counts as defined and breaks the collation (the pattern nipype's own
    ``Function`` interface uses).
    """
    undefined = {}
    for port in ports:
        base.add_trait(port, traits.Any(desc=port))
        undefined[port] = Undefined
    if undefined:
        base.trait_set(trait_change_notify=False, **undefined)
    return base


def _params_with_defaults(cls: type, given: Any) -> dict[str, Any]:
    """Schema defaults first, then whatever the pipeline set."""
    from fmriflow.modules._schema import schema_defaults

    params = dict(schema_defaults(getattr(cls, "PARAM_SCHEMA", {}) or {}))
    if isdefined(given) and given:
        params.update(dict(given))
    return params


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
        return _add_output_ports(super()._outputs(), self._out_ports)

    def _run_interface(self, runtime):
        cls = _resolve_node_cls(self.inputs.node_type)
        inputs: dict[str, Any] = {}
        for port in self._in_ports:
            value = getattr(self.inputs, port)
            if isdefined(value) and value not in (None, [], ""):
                inputs[port] = _to_path_value(value)
        params = _params_with_defaults(cls, self.inputs.params)
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

class ContainerAppInputSpec(DynamicTraitedSpec, BaseInterfaceInputSpec):
    node_type = traits.Str(mandatory=True, desc="registry name of the node class")
    params = traits.Dict(usedefault=True, desc="node parameters")
    # Bookkeeping the runner sets; must not change the node's hash.
    events_path = traits.Str(desc="JSONL file for inner nipype node events", nohash=True)
    node_path = traits.Str(desc="dotted path of this node in the run", nohash=True)
    checkpoints_path = traits.Str(desc="JSONL file for checkpoint records", nohash=True)
    run_id = traits.Str(desc="run id (checkpoint records)", nohash=True)
    subject = traits.Str(desc="subject label (checkpoint records)", nohash=True)
    abort_on_bad = traits.Bool(False, usedefault=True, desc="terminate the app on a bad checkpoint", nohash=True)
    # Content fingerprint of input directories (BIDS edits invalidate the node).
    content_fingerprint = traits.Str(desc="hash of fingerprinted inputs")


class ContainerAppInterface(BaseInterface):
    """nipype interface around a ``container_app`` node.

    The node class supplies ``build_command(inputs, params, out_dir)``
    (a list, or a string to run through the shell) and
    ``collect(inputs, params, out_dir)``. The command runs in its own
    process group with stdout+stderr in ``<node dir>/stdout.log``; when
    the class sets ``INNER_NIPYPE_LOG`` the log lines are parsed for
    nipype ``[Node]`` events and appended to ``events_path`` under this
    node's dotted path, so an app like fmriprep shows its inner DAG live.
    """

    input_spec = ContainerAppInputSpec
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
        return _add_output_ports(super()._outputs(), self._out_ports)

    def _port_values(self) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for port in self._in_ports:
            value = getattr(self.inputs, port)
            if isdefined(value) and value not in (None, [], ""):
                values[port] = _to_path_value(value)
        return values

    def _run_interface(self, runtime):
        from fmriflow.preproc.container import run_logged

        cls = _resolve_node_cls(self.inputs.node_type)
        node = cls()
        inputs = self._port_values()
        params = _params_with_defaults(cls, self.inputs.params)
        out_dir = Path(runtime.cwd)
        out_dir.mkdir(parents=True, exist_ok=True)

        validate = getattr(node, "validate", None)
        if callable(validate):
            errors = list(validate(inputs, params) or [])
            if errors:
                raise ValueError(f"{self.inputs.node_type}: " + "; ".join(errors))

        cmd = node.build_command(inputs, params, out_dir)
        log_path = out_dir / "stdout.log"
        on_line = None
        if getattr(cls, "INNER_NIPYPE_LOG", False) and isdefined(self.inputs.events_path) and self.inputs.events_path:
            from fmriflow.preproc.nipype_log import NipypeLogParser, append_jsonl

            parser = NipypeLogParser()
            events_path = Path(self.inputs.events_path)
            prefix = self.inputs.node_path if isdefined(self.inputs.node_path) and self.inputs.node_path else self.inputs.node_type

            def on_line(text: str) -> None:
                for ev in parser.feed(text):
                    ev = dict(ev)
                    ev["node"] = f"{prefix}.{ev['node']}"
                    ev["workflow"] = f"{prefix}.{ev['workflow']}" if ev.get("workflow") else prefix
                    ev["inner"] = True
                    append_jsonl(events_path, ev)

        # Live checkpoints: poll the node's declared artefacts while it runs.
        watcher = None
        abort_event = threading.Event()
        checks = list(getattr(cls, "CHECKS", []) or [])
        if checks and isdefined(self.inputs.checkpoints_path) and self.inputs.checkpoints_path:
            from fmriflow.preproc.checkpoints import CheckpointSink, CheckpointWatcher

            ctx_fn = getattr(node, "checkpoint_context", None)
            context = dict(ctx_fn(inputs, params, out_dir)) if callable(ctx_fn) else {}
            context.setdefault("node_dir", str(out_dir))
            context.setdefault("subject", str(inputs.get("subject") or ""))
            sink = CheckpointSink(
                self.inputs.checkpoints_path,
                self.inputs.events_path if isdefined(self.inputs.events_path) else None,
            )
            node_path = self.inputs.node_path if isdefined(self.inputs.node_path) and self.inputs.node_path else self.inputs.node_type
            abort = bool(self.inputs.abort_on_bad)

            def _on_bad(cp):
                if abort:
                    logger.error("checkpoint %s is bad (%s); aborting %s", cp.step, "; ".join(cp.reasons), node_path)
                    abort_event.set()

            watcher = CheckpointWatcher(
                checks, context, sink,
                run_id=self.inputs.run_id if isdefined(self.inputs.run_id) else "",
                node=node_path,
                subject=context.get("subject", ""),
                sequence=context.get("sequence") or None,
                poll_interval=float(getattr(cls, "CHECKPOINT_POLL_S", 15.0)),
                on_bad=_on_bad,
            )
            watcher.start()

        logger.info("[%s] running: %s", self.inputs.node_type, cmd if isinstance(cmd, str) else " ".join(map(str, cmd)))
        try:
            rc = run_logged(cmd, log_path, shell=isinstance(cmd, str), on_line=on_line, abort_event=abort_event)
        finally:
            # Nothing in the watcher's shutdown may replace the app's own
            # failure as the exception the run reports.
            if watcher is not None:
                try:
                    watcher.stop()
                    watcher.join(timeout=10)
                except Exception:
                    logger.exception("checkpoint watcher did not stop cleanly")
                try:
                    watcher.sweep(final=True)
                except Exception:
                    logger.exception("final checkpoint sweep failed")
        runtime.returncode = rc
        if abort_event.is_set():
            bad = [cp for cp in (watcher.results if watcher else []) if cp.verdict == "bad"]
            raise RuntimeError(
                f"{self.inputs.node_type} aborted on a bad checkpoint: "
                + "; ".join(f"{cp.step}: {', '.join(cp.reasons)}" for cp in bad)
            )
        if rc != 0:
            tail = ""
            try:
                tail = "".join(log_path.read_text(errors="replace").splitlines(True)[-30:])
            except OSError:
                pass
            raise RuntimeError(
                f"{self.inputs.node_type} exited with code {rc}; last log lines:\n{tail}"
            )
        results = node.collect(inputs, params, out_dir) or {}
        self._results = {k: _from_path_value(v) for k, v in results.items()}
        return runtime

    def _list_outputs(self):
        outputs = self._outputs().get()
        for port in self._out_ports:
            if port in getattr(self, "_results", {}):
                outputs[port] = self._results[port]
        return outputs


def make_container_interface(cls: type, params: dict[str, Any] | None = None, **inputs: Any) -> ContainerAppInterface:
    """Instantiate the interface for a ``container_app`` node class."""
    if not callable(getattr(cls, "build_command", None)):
        raise TypeError(f"{cls.__name__} has no build_command(); not a container_app node")
    name = getattr(cls, "name", None) or cls.__name__
    iface = ContainerAppInterface(node_type=name, node_cls=cls, **inputs)
    if params is not None:
        iface.inputs.params = dict(params)
    return iface


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
