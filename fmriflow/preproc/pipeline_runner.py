"""PipelineRunner — one pipeline, one nipype Workflow, one run.

Turns a :class:`~fmriflow.preproc.graph.Pipeline` plus a
:class:`~fmriflow.preproc.graph.PipelineRunRequest` into a nipype
``Workflow`` and runs it:

- ``interface`` / ``source`` nodes -> :class:`RunNodeInterface`
  (``MapNode`` when the node has ``iter``);
- ``container_app`` nodes -> :class:`ContainerAppInterface` (with the
  events file + dotted node path so the app's inner DAG streams live);
- ``composite`` nodes -> the node's own nipype ``Workflow`` embedded as a
  sub-workflow, wired through its ``inputnode`` / ``outputnode``.

Caching is nipype's own hashing. ``use_cache=False`` marks every node
``overwrite``; ``rerun_from`` marks those nodes and their descendants.
Node status goes through nipype's ``status_callback`` into the run's
``events.jsonl`` in the same shape the fmriprep log parser emits, so the
existing status strip and DAG viewer work unchanged.

After the run the manifest is assembled: the ``manifest.backend_node``
node provides the base ``PreprocManifest`` (or one is synthesised from a
source node), ``bold_from`` / ``confounds_from`` re-point the run files
at a downstream node's outputs, and one ``StepRecord`` per executed
non-source node is appended for provenance.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from fmriflow.preproc.graph import INPUT_REF_PREFIX, Pipeline, PipelineNode, PipelineRunRequest, iter_handles
from fmriflow.preproc.checkpoints import Check
from fmriflow.preproc.manifest import PreprocManifest, RunRecord, now_iso
from fmriflow.preproc.node_registry import NodeRegistry, node_ports
from fmriflow.preproc.stack import StepRecord

logger = logging.getLogger(__name__)

EventSink = Callable[[dict[str, Any]], None]


@dataclass
class NodeRunRecord:
    node_id: str
    node_type: str
    kind: str
    status: str = "pending"        # ok | failed | cached | skipped | pending
    duration_s: float = 0.0
    work_dir: str = ""
    outputs: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id, "node_type": self.node_type, "kind": self.kind,
            "status": self.status, "duration_s": self.duration_s, "work_dir": self.work_dir,
            "outputs": self.outputs, "error": self.error,
        }


@dataclass
class PipelineRunResult:
    status: str                              # completed | failed
    manifest: PreprocManifest | None
    node_records: list[NodeRunRecord]
    duration_s: float
    errors: list[str] = field(default_factory=list)
    work_dir: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "duration_s": self.duration_s,
            "errors": list(self.errors),
            "work_dir": self.work_dir,
            "n_nodes": len(self.node_records),
            "nodes": [r.to_dict() for r in self.node_records],
        }


def workflow_name(pipeline: Pipeline, request: PipelineRunRequest) -> str:
    """The nipype Workflow name — stable across runs so resume / rerun hit the cache.

    Keyed by pipeline name + subject; the work tree lives at
    ``<work_dir>/<workflow_name>/<node_id>``.
    """
    raw = f"{pipeline.name}__sub_{request.subject}"
    return re.sub(r"[^A-Za-z0-9_]", "_", raw)


class _StatusCallback:
    """Picklable handle on the runner's status callback.

    nipype stores ``plugin_args`` (including ``status_callback``) on every
    MapNode and pickles the node into its work dir; a bound method would
    drag the runner, its registry and every node class into that pickle.
    The unpickled copy is inert.
    """

    def __init__(self, runner: "PipelineRunner | None") -> None:
        self._runner = runner

    def __call__(self, node: Any, status: str) -> None:
        if self._runner is not None:
            self._runner._status_callback(node, status)

    def __getstate__(self) -> dict:
        return {}

    def __setstate__(self, state: dict) -> None:
        self._runner = None


class CompositeConfig(SimpleNamespace):
    """What a composite node's ``build(config)`` sees: the run request's
    fields plus this node's ``params``."""


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    return value


class PipelineRunner:
    """Build and run one pipeline. Not reusable across runs."""

    def __init__(
        self,
        registry: NodeRegistry,
        *,
        run_id: str = "pipeline",
        event_sink: EventSink | None = None,
        events_path: Path | str | None = None,
        crash_dir: Path | str | None = None,
        checkpoints_path: Path | str | None = None,
    ) -> None:
        self.registry = registry
        self.run_id = run_id
        self.checkpoints_path = Path(checkpoints_path) if checkpoints_path else None
        self._request: PipelineRunRequest | None = None
        self._pipeline: Pipeline | None = None
        # Set by build(): the nipype workflow name (stable per pipeline + subject).
        self.wf_name = run_id
        self.event_sink = event_sink
        self.events_path = Path(events_path) if events_path else None
        self.crash_dir = Path(crash_dir) if crash_dir else None
        self._records: dict[str, NodeRunRecord] = {}
        self._started: dict[str, float] = {}
        self._nipype_nodes: dict[str, Any] = {}
        self._exec_nodes: dict[str, Any] = {}

    # ── validation ────────────────────────────────────────────────

    def validate(self, pipeline: Pipeline, request: PipelineRunRequest) -> list[str]:
        errors = pipeline.validate(self.registry)
        if not request.subject:
            errors.append("run request needs a subject")
        if not request.output_dir:
            errors.append("run request needs an output_dir")
        for n in pipeline.nodes:
            for port, ref in n.bindings.items():
                name = ref[len(INPUT_REF_PREFIX):] if isinstance(ref, str) and ref.startswith(INPUT_REF_PREFIX) else None
                if name is None:
                    continue
                try:
                    value = request.resolve_input(name)
                except KeyError:
                    errors.append(f"node {n.id}: {ref} is not provided by the run request")
                    continue
                if value in (None, "") and pipeline.inputs.get(name, {}).get("required", True):
                    errors.append(f"node {n.id}: {ref} is empty in the run request")
            if n.iter is not None and self.registry.has(n.type) and self.registry.kind(n.type) == "composite":
                errors.append(f"node {n.id}: iter is not supported on composite nodes; put a 'select' node in front")
        for nid in request.rerun_from:
            if not pipeline.has_node(nid):
                errors.append(f"rerun_from names unknown node {nid!r}")
        return errors

    # ── build ─────────────────────────────────────────────────────

    def _emit(self, event: dict[str, Any]) -> None:
        event.setdefault("timestamp", time.time())
        if self.event_sink is not None:
            try:
                self.event_sink(event)
            except Exception:
                logger.exception("event sink failed")

    def _node_params(self, node: PipelineNode, request: PipelineRunRequest) -> dict[str, Any]:
        params = dict(node.params)
        params.update(request.params_override.get(node.id, {}))
        return params

    def _static_inputs(self, node: PipelineNode, request: PipelineRunRequest) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for port, ref in node.bindings.items():
            name = ref[len(INPUT_REF_PREFIX):]
            value = request.resolve_input(name)
            if value not in (None, ""):
                values[port] = value
        for port, value in node.literal_inputs.items():
            values[port] = value
        return values

    def _work_dir(self, request: PipelineRunRequest) -> Path:
        return Path(request.work_dir) if request.work_dir else Path(request.output_dir) / "work"

    def build(self, pipeline: Pipeline, request: PipelineRunRequest) -> Any:
        """Return the nipype ``Workflow`` for this pipeline + request."""
        from nipype import MapNode, Node, Workflow

        from fmriflow.preproc.fingerprint import _subject_mtime_hash
        from fmriflow.preproc.nipype_adapters import (
            build_composite,
            composite_ports,
            make_container_interface,
            make_interface,
        )

        work_dir = self._work_dir(request)
        work_dir.mkdir(parents=True, exist_ok=True)
        self.wf_name = workflow_name(pipeline, request)
        wf = Workflow(name=self.wf_name, base_dir=str(work_dir))
        wf.config["execution"]["crashdump_dir"] = str(self.crash_dir or work_dir / "crash")
        wf.config["execution"]["stop_on_first_crash"] = "true"
        # Text crash files: readable in the UI, and never fail on pickling.
        wf.config["execution"]["crashfile_format"] = "txt"
        wf.config["execution"]["remove_unnecessary_outputs"] = "false"

        overwrite_ids: set[str] = set()
        if not request.use_cache:
            overwrite_ids = {n.id for n in pipeline.nodes}
        elif request.rerun_from:
            overwrite_ids = pipeline.descendants(request.rerun_from)

        composite_ports_by_id: dict[str, tuple[list[str], list[str]]] = {}
        self._nipype_nodes.clear()
        self._records.clear()

        for node in pipeline.topo_order():
            cls = self.registry.cls(node.type)
            kind = self.registry.kind(node.type)
            params = self._node_params(node, request)
            static = self._static_inputs(node, request)
            self._records[node.id] = NodeRunRecord(node_id=node.id, node_type=node.type, kind=kind)

            if kind == "composite":
                config = CompositeConfig(**request.to_dict(), params=params, node_id=node.id)
                sub = build_composite(cls, config)
                if sub is None:
                    self._records[node.id].status = "skipped"
                    logger.info("composite node %s built nothing; skipped", node.id)
                    continue
                # clone() renames the workflow *and* re-derives the node
                # hierarchy; assigning .name after construction does not.
                if sub.name != node.id:
                    sub = sub.clone(node.id)
                ins, outs = composite_ports(sub)
                composite_ports_by_id[node.id] = (ins, outs)
                inputnode = sub.get_node("inputnode")
                for port, value in static.items():
                    if inputnode is not None and port in ins:
                        setattr(inputnode.inputs, port, _jsonable(value))
                wf.add_nodes([sub])
                self._nipype_nodes[node.id] = sub
                continue

            if kind == "container_app":
                iface = make_container_interface(cls, params=params)
                if self.events_path is not None:
                    iface.inputs.events_path = str(self.events_path)
                iface.inputs.node_path = f"{self.wf_name}.{node.id}"
                if self.checkpoints_path is not None:
                    iface.inputs.checkpoints_path = str(self.checkpoints_path)
                iface.inputs.run_id = self.run_id
                iface.inputs.subject = request.subject
                iface.inputs.abort_on_bad = bool(request.abort_on_bad)
                fp_inputs = list(getattr(cls, "FINGERPRINT_INPUTS", []) or [])
                parts = []
                for port in fp_inputs:
                    value = static.get(port)
                    if value:
                        parts.append(_subject_mtime_hash(Path(str(value)), request.subject))
                if parts:
                    iface.inputs.content_fingerprint = "|".join(parts)
            else:
                iface = make_interface(cls, params=params)

            if node.iter is not None:
                handles = iter_handles(node.iter)
                nn = MapNode(iface, name=node.id, iterfield=handles)
                if "values" in node.iter:
                    setattr(nn.inputs, handles[0], _jsonable(node.iter["values"]))
            else:
                nn = Node(iface, name=node.id)
            for port, value in static.items():
                setattr(nn.inputs, port, _jsonable(value))
            if node.id in overwrite_ids:
                nn.overwrite = True
            wf.add_nodes([nn])
            self._nipype_nodes[node.id] = nn

        for edge in pipeline.edges:
            src = self._nipype_nodes.get(edge.source)
            dst = self._nipype_nodes.get(edge.target)
            if src is None or dst is None:
                # A skipped composite: nothing to connect.
                continue
            src_field = edge.source_handle
            dst_field = edge.target_handle
            if edge.source in composite_ports_by_id:
                src_field = f"outputnode.{src_field}"
            if edge.target in composite_ports_by_id:
                dst_field = f"inputnode.{dst_field}"
            wf.connect(src, src_field, dst, dst_field)

        return wf

    # ── status callback ───────────────────────────────────────────

    def _status_callback(self, node: Any, status: str) -> None:
        full = getattr(node, "fullname", None) or getattr(node, "name", "?")
        wf_path, _, leaf = full.rpartition(".")
        top = full.split(".")[1] if "." in full else full
        now = time.time()
        if status == "start":
            self._started[full] = now
            self._emit({"event": "node_start", "node": full, "workflow": wf_path, "leaf": leaf, "t": now, "level": "INFO"})
            return
        started = self._started.pop(full, now)
        if status == "exception":
            rec = self._records.get(top)
            if rec is not None and rec.status == "pending":
                rec.status = "failed"
                rec.duration_s = now - started
            self._emit({"event": "node_fail", "node": full, "workflow": wf_path, "leaf": leaf, "t": now, "level": "ERROR"})
            return
        cached = False
        try:
            result_file = Path(node.output_dir()) / f"result_{node.name}.pklz"
            cached = result_file.exists() and result_file.stat().st_mtime < started - 0.001
        except Exception:
            pass
        rec = self._records.get(top)
        if rec is not None and (leaf == top or leaf == "outputnode"):
            rec.status = "cached" if cached else "ok"
            rec.duration_s = now - started
        self._emit({
            "event": "node_done", "node": full, "workflow": wf_path, "leaf": leaf,
            "t": now, "level": "INFO", "cached": cached, "duration_s": now - started,
        })
        if rec is not None and leaf == top and rec.kind in ("interface", "source"):
            self._output_checkpoints(node, rec, full)

    def _output_checkpoints(self, node: Any, rec: NodeRunRecord, full: str) -> None:
        """Generic per-output checks for a finished interface/source node."""
        from fmriflow.preproc.checkpoints import (
            CheckpointSink, evaluate, generic_output_checks, worst_verdict,
        )

        if self.checkpoints_path is None or self._request is None:
            return
        try:
            cls = self.registry.cls(rec.node_type)
        except KeyError:
            return
        checks = generic_output_checks(cls)
        if not checks:
            return
        outputs = _result_outputs(node)
        sink = CheckpointSink(self.checkpoints_path, self.events_path)
        verdicts: list[str] = []
        bad_reasons: list[str] = []
        for port, check in checks:
            value = outputs.get(port)
            files = value if isinstance(value, list) else [value] if value else []
            for i, f in enumerate(files):
                step = check.step if len(files) == 1 else f"{check.step}[{i}]"
                cp = evaluate(
                    Check(step=step, artifact=port, metrics=check.metrics, norms_key=check.norms_key, live=False),
                    Path(str(f)), run_id=self.run_id, node=full, subject=self._request.subject,
                )
                sink.write(cp)
                verdicts.append(cp.verdict)
                if cp.verdict == "bad":
                    bad_reasons.append(f"{step}: {', '.join(cp.reasons)}")
        if bad_reasons and self._request.abort_on_bad:
            raise RuntimeError(f"node {rec.node_id} produced a bad output: " + "; ".join(bad_reasons))
        rec.error = rec.error if not bad_reasons else "; ".join(bad_reasons)

    # ── run ───────────────────────────────────────────────────────

    def run(self, pipeline: Pipeline, request: PipelineRunRequest) -> PipelineRunResult:
        t0 = time.time()
        errors = self.validate(pipeline, request)
        if errors:
            self._emit({"event": "failed", "errors": errors})
            return PipelineRunResult(status="failed", manifest=None, node_records=[], duration_s=0.0, errors=errors)

        self._request = request
        self._pipeline = pipeline
        wf = self.build(pipeline, request)
        self._emit({
            "event": "started", "subject": request.subject, "pipeline": pipeline.name,
            "run_id": self.run_id, "workflow": self.wf_name,
            "n_nodes": len(pipeline.nodes), "nodes": [n.id for n in pipeline.nodes],
        })
        work_dir = Path(wf.base_dir)
        plugin_args: dict[str, Any] = {"status_callback": _StatusCallback(self)}
        if request.plugin == "MultiProc" and request.n_procs:
            plugin_args["n_procs"] = int(request.n_procs)

        try:
            execgraph = wf.run(plugin=request.plugin or "Linear", plugin_args=plugin_args)
        except Exception as e:
            logger.exception("pipeline %s failed", pipeline.name)
            failed = [r for r in self._records.values() if r.status == "failed"]
            msg = f"{type(e).__name__}: {e}"
            for r in failed:
                r.error = msg
            errs = [msg] + [f"node {r.node_id} failed" for r in failed]
            self._emit({"event": "failed", "errors": errs})
            return PipelineRunResult(
                status="failed", manifest=None, node_records=list(self._records.values()),
                duration_s=time.time() - t0, errors=errs, work_dir=str(work_dir),
            )

        outputs_by_id = self._collect_outputs(execgraph, pipeline)
        for nid, outs in outputs_by_id.items():
            rec = self._records[nid]
            rec.outputs = _jsonable(outs)
            rec.work_dir = str(work_dir / self.wf_name / nid)
            if rec.status == "pending":
                rec.status = "ok"
        # A composite whose inner nodes all ran (or were cached) is done even
        # though nipype pruned its identity in/out nodes from the callbacks.
        for rec in self._records.values():
            if rec.kind == "composite" and rec.status == "pending":
                rec.status = "ok"
                rec.work_dir = str(work_dir / self.wf_name / rec.node_id)

        manifest: PreprocManifest | None = None
        try:
            manifest = self._build_manifest(pipeline, request, outputs_by_id)
        except Exception as e:
            logger.exception("manifest assembly failed")
            errs = [f"manifest: {type(e).__name__}: {e}"]
            self._emit({"event": "failed", "errors": errs})
            return PipelineRunResult(
                status="failed", manifest=None, node_records=list(self._records.values()),
                duration_s=time.time() - t0, errors=errs, work_dir=str(work_dir),
            )

        duration = time.time() - t0
        self._emit({"event": "completed", "n_nodes": len(pipeline.nodes), "duration_s": duration})
        return PipelineRunResult(
            status="completed", manifest=manifest, node_records=list(self._records.values()),
            duration_s=duration, errors=[], work_dir=str(work_dir),
        )

    # ── outputs + manifest ────────────────────────────────────────

    def _collect_outputs(self, execgraph: Any, pipeline: Pipeline) -> dict[str, dict[str, Any]]:
        """``{node_id: {port: value}}`` for every top-level node that ran."""
        outputs: dict[str, dict[str, Any]] = {}
        exec_by_fullname: dict[str, Any] = {}
        for nn in execgraph.nodes():
            full = getattr(nn, "fullname", nn.name)
            parts = full.split(".")
            if len(parts) < 2:
                continue
            top = parts[1]
            if top not in self._records:
                continue
            if len(parts) != 2:
                exec_by_fullname[full] = nn
                continue
            outputs[top] = _result_outputs(nn)
            # The executed copy carries base_dir + hash; the originals do not.
            self._exec_nodes[top] = nn
        # Composites: nipype prunes the identity outputnode, so read each
        # output port from the inner node that feeds it.
        for nid, rec in self._records.items():
            if rec.kind != "composite" or nid in outputs:
                continue
            sub = self._nipype_nodes.get(nid)
            if sub is None:
                continue
            outputs[nid] = self._composite_outputs(nid, sub, exec_by_fullname)
        return outputs

    def _composite_outputs(self, nid: str, sub: Any, exec_by_fullname: dict[str, Any]) -> dict[str, Any]:
        outs: dict[str, Any] = {}
        try:
            outputnode = sub.get_node("outputnode")
        except Exception:
            outputnode = None
        if outputnode is None:
            return outs
        graph = getattr(sub, "_graph", None)
        if graph is None:
            return outs
        for src, _dst, data in graph.in_edges(outputnode, data=True):
            for (src_field, dst_field) in data.get("connect", []):
                if not isinstance(src_field, str):
                    continue
                exec_node = exec_by_fullname.get(f"{self.wf_name}.{nid}.{src.name}")
                if exec_node is None:
                    continue
                value = _result_outputs(exec_node).get(src_field)
                if value is not None:
                    outs[dst_field] = value
        return outs

    def _run_records(self, files: list[Path], base: Path, confounds: list[Path] | None = None) -> list[RunRecord]:
        records: list[RunRecord] = []
        for i, f in enumerate(files):
            shape, n_trs = _nifti_info(f)
            try:
                rel = str(Path(f).relative_to(base))
            except ValueError:
                rel = str(f)
            conf = None
            if confounds and i < len(confounds):
                try:
                    conf = str(Path(confounds[i]).relative_to(base))
                except ValueError:
                    conf = str(confounds[i])
            records.append(RunRecord(run_name=Path(f).name.split("_bold")[0].split("_desc")[0] or f"run-{i+1:02d}",
                                     source_file="", output_file=rel, n_trs=n_trs, shape=shape,
                                     confounds_file=conf))
        return records

    def _base_manifest(self, pipeline: Pipeline, request: PipelineRunRequest,
                       outputs_by_id: dict[str, dict[str, Any]]) -> PreprocManifest:
        backend_id = pipeline.manifest.get("backend_node")
        if not backend_id:
            # No backend declared: an empty manifest rooted at output_dir.
            return PreprocManifest(
                subject=request.subject, dataset=request.dataset, sessions=list(request.sessions), runs=[],
                backend="pipeline", backend_version="", parameters={"pipeline": pipeline.name},
                space="native", output_dir=str(request.output_dir), created=now_iso(),
            )
        node = pipeline.node(backend_id)
        cls = self.registry.cls(node.type)
        kind = self.registry.kind(node.type)
        outs = outputs_by_id.get(backend_id, {})
        node_dir = self._work_dir(request) / self.wf_name / backend_id
        params = self._node_params(node, request)

        if kind == "container_app":
            manifest_path = outs.get("manifest")
            if manifest_path and Path(str(manifest_path)).is_file():
                return PreprocManifest.from_dict(json.loads(Path(str(manifest_path)).read_text()))
            return cls().to_manifest(self._static_inputs(node, request), params, node_dir)

        if kind == "composite":
            config = CompositeConfig(**request.to_dict(), params=params, node_id=backend_id)
            to_manifest = getattr(cls(), "to_manifest", None)
            m = to_manifest(config, outs) if callable(to_manifest) else None
            if m is not None:
                return m
            bold = outs.get("bold_mc") or outs.get("bold") or outs.get("out_file")
            files = [Path(b) for b in (bold if isinstance(bold, list) else [bold] if bold else [])]
            return PreprocManifest(
                subject=request.subject, dataset=request.dataset, sessions=list(request.sessions),
                runs=self._run_records(files, node_dir), backend=node.type,
                backend_version=str(getattr(cls, "version", "")), parameters=params,
                space="native", output_dir=str(node_dir), created=now_iso(),
            )

        # source nodes
        if node.type == "manifest_source":
            static = self._static_inputs(node, request)
            mp = static.get("manifest")
            if mp:
                return PreprocManifest.from_dict(json.loads(Path(str(mp)).read_text()))
        bold = outs.get("bold") or []
        files = [Path(b) for b in (bold if isinstance(bold, list) else [bold])]
        conf = outs.get("confounds") or []
        confs = [Path(c) for c in (conf if isinstance(conf, list) else [conf])] if conf else None
        base = Path(str(request.derivatives_dir or self._static_inputs(node, request).get("derivatives_dir") or request.output_dir))
        return PreprocManifest(
            subject=request.subject, dataset=request.dataset, sessions=list(request.sessions),
            runs=self._run_records(files, base, confs), backend=node.type,
            backend_version=str(getattr(cls, "version", "")), parameters=params,
            space="native", output_dir=str(base), created=now_iso(),
        )

    def _build_manifest(self, pipeline: Pipeline, request: PipelineRunRequest,
                        outputs_by_id: dict[str, dict[str, Any]]) -> PreprocManifest:
        manifest = self._base_manifest(pipeline, request, outputs_by_id)
        runs = list(manifest.runs)
        output_dir = manifest.output_dir

        bold_ref = pipeline.manifest.get("bold_from")
        if bold_ref:
            nid, _, port = str(bold_ref).partition(".")
            produced = outputs_by_id.get(nid, {}).get(port)
            files = [Path(p) for p in (produced if isinstance(produced, list) else [produced] if produced else [])]
            if files:
                node_dir = self._work_dir(request) / self.wf_name / nid
                conf_ref = pipeline.manifest.get("confounds_from")
                confs: list[Path] | None = None
                if conf_ref:
                    cnid, _, cport = str(conf_ref).partition(".")
                    cv = outputs_by_id.get(cnid, {}).get(cport)
                    confs = [Path(c) for c in (cv if isinstance(cv, list) else [cv] if cv else [])]
                new_runs = self._run_records(files, node_dir, confs)
                # Keep run names from the base manifest when the counts line up.
                if runs and len(runs) == len(new_runs):
                    new_runs = [RunRecord(run_name=old.run_name, source_file=old.source_file,
                                          output_file=new.output_file, n_trs=new.n_trs, shape=new.shape,
                                          n_voxels=old.n_voxels, confounds_file=new.confounds_file or old.confounds_file,
                                          qc=old.qc) for old, new in zip(runs, new_runs)]
                runs = new_runs
                output_dir = str(node_dir)

        steps = list(manifest.additional_steps)
        for node in pipeline.topo_order():
            rec = self._records.get(node.id)
            if rec is None or rec.kind == "source" or rec.status == "skipped":
                continue
            if node.id == pipeline.manifest.get("backend_node"):
                continue
            fingerprint = _node_hash(self._exec_nodes.get(node.id) or self._nipype_nodes.get(node.id))
            steps.append(StepRecord(
                name=node.type, version=str(getattr(self.registry.cls(node.type), "version", "")),
                params=self._node_params(node, request), output_dir=rec.work_dir,
                duration_s=rec.duration_s, fingerprint=fingerprint,
            ))

        return PreprocManifest(
            subject=manifest.subject, dataset=manifest.dataset, sessions=list(manifest.sessions),
            runs=runs, backend=manifest.backend, backend_version=manifest.backend_version,
            parameters=dict(manifest.parameters), space=manifest.space, resolution=manifest.resolution,
            confounds_applied=list(manifest.confounds_applied), additional_steps=steps,
            output_dir=output_dir, output_format=manifest.output_format, file_pattern=manifest.file_pattern,
            created=now_iso(), pipeline_version=manifest.pipeline_version, checksum=None,
            freesurfer_subjects_dir=manifest.freesurfer_subjects_dir, autoflatten=manifest.autoflatten,
            manifest_version=manifest.manifest_version,
        )


def _result_outputs(nn: Any) -> dict[str, Any]:
    """A node's result outputs as a plain dict (TraitedSpec or MapNode Bunch)."""
    try:
        res = nn.result
    except Exception:
        return {}
    outs = getattr(res, "outputs", None) if res is not None else None
    if outs is None:
        return {}
    if hasattr(outs, "trait_get"):
        raw = outs.trait_get()
    elif hasattr(outs, "items"):
        raw = dict(outs.items())
    else:
        raw = dict(vars(outs))
    clean: dict[str, Any] = {}
    for k, v in raw.items():
        if k.startswith("_"):
            continue
        try:
            from nipype.interfaces.base import isdefined
            if not isdefined(v):
                continue
        except Exception:
            pass
        clean[k] = v
    return clean


def _node_hash(nn: Any) -> str:
    """nipype's content hash for a node (what its cache key is)."""
    if nn is None:
        return ""
    try:
        value = nn._get_hashval()[1]
        if value:
            return str(value)
    except Exception:
        pass
    # nipype writes ``_0x<hash>.json`` into the node dir once it has run.
    try:
        for f in Path(nn.output_dir()).glob("_0x*.json"):
            return f.stem[3:]
    except Exception:
        pass
    return ""


def _nifti_info(path: Path) -> tuple[list[int], int]:
    try:
        import nibabel as nib
        img = nib.load(str(path))
        shape = [int(s) for s in img.shape]
        return shape, (shape[3] if len(shape) > 3 else 1)
    except Exception:
        return [], 0
