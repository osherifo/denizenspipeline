"""Run an analysis graph in-process.

Nodes run one at a time in topological order; among nodes that are ready,
earlier stages go first, so a graph compiled from stage YAML runs in the
same order as the stage orchestrator and its stage events stay contiguous.
Values pass in memory along edges.

The run summary, events, intermediates and QA outputs follow the stage
orchestrator's formats, so dashboards and run views work unchanged:

- a :class:`~fmriflow.core.run_summary.NodeRecord` per node (kind =
  category, ``utility`` for utility nodes), grouped into stage records;
- ``stage_*`` events when the stage changes, ``node_start/done/fail`` per
  node, plus ``node_skipped`` when a required upstream value is missing;
- stage outputs are put on a run :class:`~fmriflow.context.PipelineContext`
  that drives intermediate dumps and stage QA and is returned at the end.

Failure policy per node: ``fail`` stops the run (as a stage failure);
``isolate`` records the node as failed, passes its incoming context through
and lets the run continue.
"""

from __future__ import annotations

import copy
import heapq
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fmriflow import ui as fui
from fmriflow.analysis.adapters import NodeEnv
from fmriflow.analysis.catalog import NodeCatalog
from fmriflow.analysis.compile_legacy import compile_subject_config
from fmriflow.analysis.graph import AnalysisGraph
from fmriflow.analysis.values import ContextValue, merge_contexts
from fmriflow.context import PipelineContext
from fmriflow.core.run_summary import NodeIdGen, NodeRecord, RunSummary, StageRecord
from fmriflow.core.stages import GROUP_MODULE_STAGES, STUDY_MODULE_STAGES, SUBJECT_STAGES
from fmriflow.exceptions import ConfigError, StageError
from fmriflow.graph.model import INPUT_REF_PREFIX
from fmriflow.graph.ports import accepts_many
from fmriflow.orchestrator import _record, _relativize

logger = logging.getLogger(__name__)

_STAGE_RANK = {s: i for i, s in enumerate((*SUBJECT_STAGES, *GROUP_MODULE_STAGES, *STUDY_MODULE_STAGES))}
_EMPTY_STAGE_DETAIL = {"features": "0 feature(s)", "analyze": "skipped (none configured)",
                       "report": "0 artifact(s) saved"}


class Cancelled(RuntimeError):
    """The run was cancelled between nodes."""


def _substitute(value: Any, inputs: dict[str, Any], used: set[str]) -> Any:
    if isinstance(value, str) and value.startswith(INPUT_REF_PREFIX):
        name = value[len(INPUT_REF_PREFIX):]
        used.add(name)
        return inputs.get(name)
    if isinstance(value, dict):
        return {k: _substitute(v, inputs, used) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute(v, inputs, used) for v in value]
    return value


def resolve_graph_inputs(graph: AnalysisGraph, inputs: dict[str, Any] | None = None) -> tuple[AnalysisGraph, dict[str, Any]]:
    """Bind graph inputs: ``"$inputs.<name>"`` strings in globals, node params
    and literal inputs become the given values (or the input's ``default``).

    Returns the bound copy and the resolved inputs. ``ConfigError`` lists
    references to undeclared inputs and required inputs without a value.
    """
    given = dict(inputs or {})
    resolved: dict[str, Any] = {}
    for name, spec in graph.inputs.items():
        if name in given and given[name] not in (None, ""):
            resolved[name] = given[name]
        elif isinstance(spec, dict) and spec.get("default") is not None:
            resolved[name] = spec["default"]
    for name, value in given.items():
        if name not in graph.inputs and value not in (None, ""):
            resolved[name] = value

    bound = AnalysisGraph.from_dict(graph.to_dict())
    used: set[str] = set()
    bound.globals = _substitute(bound.globals, resolved, used)
    for node in bound.nodes:
        node.params = _substitute(node.params, resolved, used)
        node.literal_inputs = _substitute(node.literal_inputs, resolved, used)
    used.update(ref[len(INPUT_REF_PREFIX):] for n in bound.nodes for ref in n.bindings.values()
                if isinstance(ref, str) and ref.startswith(INPUT_REF_PREFIX))

    errors = [f"'$inputs.{name}' is used but the graph declares no input {name!r}"
              for name in sorted(used) if name not in graph.inputs]
    for name, spec in graph.inputs.items():
        required = not isinstance(spec, dict) or spec.get("required", True)
        if name in used and required and resolved.get(name) is None:
            errors.append(f"graph input {name!r} needs a value")
    if errors:
        raise ConfigError(errors)
    return bound, resolved


def check_graph(graph: AnalysisGraph, catalog: Any, inputs: dict[str, Any] | None = None) -> list[str]:
    """Every problem that would stop ``graph`` from running: structure and port
    types, input bindings (``run_defaults.inputs`` overlaid with ``inputs``), and
    each module's own config check on the bound graph."""
    errors = graph.validate(catalog)
    if errors:
        return errors
    given = dict((graph.run_defaults or {}).get("inputs") or {})
    given.update(inputs or {})
    try:
        bound, _ = resolve_graph_inputs(graph, given)
    except ConfigError as e:
        return list(getattr(e, "errors", None) or [str(e)])
    return GraphExecutor(catalog).validate(bound)


class _FixedId:
    """NodeIdGen stand-in for ``_record``: the graph already names the node."""

    def __init__(self, node_id: str) -> None:
        self.node_id = node_id

    def make(self, name: str) -> str:
        return self.node_id


@dataclass
class _Stage:
    name: str
    t0: float
    nodes: list[NodeRecord] = field(default_factory=list)
    analyzers_run: int = 0
    analyzers_failed: list[str] = field(default_factory=list)
    reporter_errors: list[tuple[str, BaseException]] = field(default_factory=list)
    feature_count: int = 0


class GraphExecutor:
    def __init__(self, catalog: NodeCatalog, *, cancel: threading.Event | None = None) -> None:
        self.catalog = catalog
        self.cancel = cancel
        self.last_context: PipelineContext | None = None

    # ── validation ─────────────────────────────────────────────────

    def _env(self, graph: AnalysisGraph, node_id: str, **extra: Any) -> NodeEnv:
        output_dir = (graph.globals.get("reporting") or {}).get("output_dir")
        return NodeEnv(node_id=node_id, globals=graph.globals, registry=self.catalog.registry,
                       output_dir=output_dir, **extra)

    def validate(self, graph: AnalysisGraph) -> list[str]:
        errors = graph.validate(self.catalog)
        if errors:
            return errors
        for node in graph.nodes:
            try:
                node_errors = self.catalog.validate_node(node.type, node.params, self._env(graph, node.id))
            except Exception as exc:  # a module's own check blew up
                node_errors = [f"validation raised {type(exc).__name__}: {exc}"]
            errors.extend(f"node {node.id}: {e}" for e in node_errors)
        return errors

    # ── scheduling ─────────────────────────────────────────────────

    def schedule(self, graph: AnalysisGraph) -> list:
        index = {n.id: i for i, n in enumerate(graph.nodes)}
        indegree = {n.id: 0 for n in graph.nodes}
        successors: dict[str, list[str]] = {n.id: [] for n in graph.nodes}
        for e in graph.edges:
            indegree[e.target] += 1
            successors[e.source].append(e.target)
        by_id = {n.id: n for n in graph.nodes}

        def key(node_id: str) -> tuple[int, int, str]:
            return (_STAGE_RANK.get(self.catalog.stage(by_id[node_id].type), 50), index[node_id], node_id)

        ready = [key(nid) for nid, d in indegree.items() if d == 0]
        heapq.heapify(ready)
        order = []
        while ready:
            *_, nid = heapq.heappop(ready)
            order.append(by_id[nid])
            for nxt in successors[nid]:
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    heapq.heappush(ready, key(nxt))
        if len(order) != len(graph.nodes):
            raise ConfigError(graph.CYCLE_MESSAGE)
        return order

    # ── run ────────────────────────────────────────────────────────

    def run(self, graph: AnalysisGraph, *, write_graph: bool = False,
            inputs: dict[str, Any] | None = None) -> PipelineContext:
        graph, self._run_inputs = resolve_graph_inputs(graph, inputs)
        run_ctx = PipelineContext(graph.globals)
        self.last_context = run_ctx

        errors = self.validate(graph)
        if errors:
            fui.config_error(errors)
            raise ConfigError(errors)
        order = self.schedule(graph)

        output_dir = (graph.globals.get("reporting") or {}).get("output_dir")
        if write_graph and output_dir:
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            (Path(output_dir) / "graph.json").write_text(json.dumps(graph.to_dict(), indent=2, default=str))

        values: dict[tuple[str, str], Any] = {}
        failed: set[str] = set()
        records: list[StageRecord] = []
        started_at = datetime.now(timezone.utc).isoformat()
        run_start = time.time()
        stage: _Stage | None = None

        try:
            for node in order:
                if self.cancel is not None and self.cancel.is_set():
                    raise Cancelled("run cancelled")
                node_stage = self.catalog.stage(node.type)
                if stage is None or node_stage != stage.name:
                    if stage is not None:
                        self._append(graph, records, self._guard(stage, records, lambda s=stage: self._close_stage(s, run_ctx)), run_ctx)
                    for empty in self._declared_before(graph, records, node_stage):
                        self._append(graph, records, self._empty_stage(empty), run_ctx)
                    stage = _Stage(name=node_stage, t0=fui.stage_start(node_stage))
                current = stage
                self._guard(current, records, lambda n=node, s=current: self._run_node(graph, n, s, values, run_ctx, failed))
            if stage is not None:
                self._append(graph, records, self._guard(stage, records, lambda s=stage: self._close_stage(s, run_ctx)), run_ctx)
            recorded = {r.name for r in records}
            for name in graph.stages:
                if name not in recorded:
                    self._append(graph, records, self._empty_stage(name), run_ctx)
        finally:
            run_ctx.run_summary = RunSummary(
                experiment=graph.globals.get("experiment", ""),
                subject=graph.globals.get("subject", ""),
                started_at=started_at,
                finished_at=datetime.now(timezone.utc).isoformat(),
                total_elapsed_s=round(time.time() - run_start, 3),
                stages=records,
                config_snapshot=copy.deepcopy(graph.globals),
            )
        return run_ctx

    def _append(self, graph: AnalysisGraph, records: list[StageRecord], record: StageRecord,
                run_ctx: PipelineContext) -> None:
        """Record a finished stage and, with ``checkpoint: true``, save the context
        like the stage orchestrator does after every successful stage."""
        records.append(record)
        if graph.globals.get("checkpoint") and record.status != "failed":
            run_ctx.save_checkpoint(record.name)

    def _guard(self, stage: _Stage, records: list[StageRecord], fn):
        """Run ``fn``; on failure record the stage as failed like the stage orchestrator."""
        try:
            return fn()
        except ConfigError:
            records.append(StageRecord(name=stage.name, status="failed", elapsed_s=round(time.time() - stage.t0, 3),
                                       detail="config error", nodes=list(stage.nodes)))
            fui.stage_fail(stage.name, stage.t0)
            raise
        except Cancelled as exc:
            records.append(StageRecord(name=stage.name, status="failed", elapsed_s=round(time.time() - stage.t0, 3),
                                       detail="cancelled", nodes=list(stage.nodes)))
            fui.stage_fail(stage.name, stage.t0, str(exc))
            raise
        except Exception as exc:
            records.append(StageRecord(name=stage.name, status="failed", elapsed_s=round(time.time() - stage.t0, 3),
                                       detail=str(exc), nodes=list(stage.nodes)))
            fui.stage_fail(stage.name, stage.t0, str(exc))
            raise StageError(stage.name, exc) from exc

    def _declared_before(self, graph: AnalysisGraph, records: list[StageRecord], stage_name: str) -> list[str]:
        if stage_name not in graph.stages:
            return []
        recorded = {r.name for r in records}
        out = []
        for name in graph.stages:
            if name == stage_name:
                break
            if name not in recorded:
                out.append(name)
        return out

    def _empty_stage(self, name: str) -> StageRecord:
        t0 = fui.stage_start(name)
        detail = _EMPTY_STAGE_DETAIL.get(name, "")
        fui.stage_done(name, t0, detail)
        return StageRecord(name=name, status="ok", elapsed_s=round(time.time() - t0, 3), detail=detail, nodes=[])

    def _close_stage(self, stage: _Stage, run_ctx: PipelineContext) -> StageRecord:
        name = stage.name
        by_kind = {n.kind: n for n in reversed(stage.nodes)}
        status = "ok"
        if name == "stimuli":
            detail = by_kind["stimulus_loader"].detail if "stimulus_loader" in by_kind else ""
        elif name == "responses":
            detail = by_kind["response_loader"].detail if "response_loader" in by_kind else ""
        elif name == "features":
            detail = f"{stage.feature_count} feature(s)"
        elif name == "prepare":
            detail = by_kind["preparer"].detail if "preparer" in by_kind else ""
        elif name == "model":
            detail = by_kind["model"].detail if "model" in by_kind else ""
        elif name == "analyze":
            if stage.analyzers_run == 0:
                detail = "skipped (none configured)"
            elif stage.analyzers_failed:
                n_ok = stage.analyzers_run - len(stage.analyzers_failed)
                detail = (f"{n_ok}/{stage.analyzers_run} analyzer(s) ok, "
                          f"failed: {', '.join(stage.analyzers_failed)}")
            else:
                detail = f"{stage.analyzers_run} analyzer(s)"
        elif name == "report":
            n = sum(len(v) for v in run_ctx.artifacts.values())
            if stage.reporter_errors:
                names = ", ".join(n_ for n_, _ in stage.reporter_errors)
                detail = f"{n} artifact(s) saved, {len(stage.reporter_errors)} failed: {names}"
                if not run_ctx.artifacts:
                    raise StageError("report", stage.reporter_errors[0][1])
                status = "warning"
            else:
                detail = f"{n} artifact(s) saved"
        else:
            detail = f"{len(stage.nodes)} node(s)"
        if status == "warning":
            fui.stage_warn(name, stage.t0, detail)
        else:
            fui.stage_done(name, stage.t0, detail)
        return StageRecord(name=name, status=status, elapsed_s=round(time.time() - stage.t0, 3),
                           detail=detail, nodes=list(stage.nodes))

    # ── one node ───────────────────────────────────────────────────

    def _gather_inputs(self, graph: AnalysisGraph, node, values: dict, failed: set[str]) -> tuple[dict, list[str]]:
        in_ports, _ = self.catalog.node_ports(node)
        inputs: dict[str, Any] = {}
        missing: list[str] = []
        incoming = graph.predecessors(node.id)
        for port, spec in in_ports.items():
            edges = [e for e in incoming if e.target_handle == port]
            if edges:
                got = []
                for e in edges:
                    key = (e.source, e.source_handle)
                    if key in values:
                        got.append(values[key])
                    elif e.source in failed and spec.get("required"):
                        missing.append(e.source)
                if got:
                    inputs[port] = got if accepts_many(spec) else got[0]
            elif port in node.literal_inputs:
                inputs[port] = node.literal_inputs[port]
            elif port in node.bindings:
                name = node.bindings[port].split(".", 1)[1]
                inputs[port] = self._run_inputs.get(name)
        return inputs, sorted(set(missing))

    def _run_node(self, graph: AnalysisGraph, node, stage: _Stage, values: dict,
                  run_ctx: PipelineContext, failed: set[str]) -> None:
        category = self.catalog.kind(node.type)
        adapter = self.catalog.adapter(node.type)
        module = self.catalog.module_name(node.type)
        kind = "utility" if category == "utility" else adapter.prefix
        _, out_ports = self.catalog.node_ports(node)

        inputs, missing = self._gather_inputs(graph, node, values, failed)
        if missing:
            detail = f"skipped: upstream {', '.join(missing)} failed"
            stage.nodes.append(NodeRecord(id=node.id, kind=kind, name=module, status="skipped",
                                          elapsed_s=0.0, detail=detail))
            fui.emit_event({"event": "node_skipped", "node_id": node.id, "kind": kind, "name": module,
                            "detail": detail})
            if "context" in out_ports and "context" in inputs:
                values[(node.id, "context")] = merge_contexts(inputs["context"])
            else:
                failed.add(node.id)
            return

        step_records: list[NodeRecord] = []
        env_extra: dict[str, Any] = {}
        if category == "preparers":
            step_ids = NodeIdGen("prepare")
            compiled = node.id == step_ids.make(module)

            def on_step(step_name: str, elapsed: float, error: BaseException | None) -> None:
                step_id = step_ids.make(step_name) if compiled else f"{node.id}.{step_name}"
                step_records.append(NodeRecord(
                    id=step_id, kind="preparation_step", name=step_name,
                    status="failed" if error else "ok", elapsed_s=round(elapsed, 3),
                    detail=str(error) if error else "ok"))
            env_extra["step_callback"] = on_step

        env = self._env(graph, node.id, **env_extra)
        isolate = adapter.error_policy == "isolate"
        if category == "reporters":
            # The report stage needs a model result before any reporter runs; without one the
            # stage fails as a whole (as in the stage orchestrator), not reporter by reporter.
            merge_contexts(inputs.get("context")).to_context(graph.globals).get("result")
        if category == "analyzers":
            stage.analyzers_run += 1

        with _record(stage.nodes, _FixedId(node.id), kind, module, isolate=isolate) as rec:
            try:
                if category == "models":
                    with fui.model_live():
                        outputs = self.catalog.invoke(node.type, inputs, node.params, env)
                else:
                    outputs = self.catalog.invoke(node.type, inputs, node.params, env)
            except Exception as exc:
                if category == "analyzers":
                    logger.error("Analyzer '%s' failed: %s", module, exc, exc_info=True)
                    stage.analyzers_failed.append(module)
                elif category == "reporters":
                    logger.error("Reporter '%s' failed: %s", module, exc, exc_info=True)
                    stage.reporter_errors.append((module, exc))
                if isolate:
                    if "context" in out_ports and "context" in inputs:
                        values[(node.id, "context")] = merge_contexts(inputs["context"])
                    else:
                        failed.add(node.id)
                raise
            for port, value in outputs.items():
                values[(node.id, port)] = value
            self._after_node(category, node, module, adapter, outputs, rec, run_ctx, stage, env)

        if category == "preparers" and rec.status == "ok":
            stage.nodes.extend(step_records)

    def _after_node(self, category, node, module, adapter, outputs, rec, run_ctx, stage, env) -> None:
        if category == "stimulus_loaders":
            stimuli = outputs["stimuli"]
            run_ctx.put("stimuli", stimuli)
            run_ctx.dump_intermediate("stimuli", stimuli, rec)
            run_ctx.run_stage_qa("stimuli", stimuli, rec)
            n = len(stimuli.runs)
            rec.detail = f"{n} runs" if n else f"skipped ({module})"
        elif category == "response_loaders":
            responses = outputs["responses"]
            run_ctx.put("responses", responses)
            run_ctx.dump_intermediate("responses", responses, rec)
            run_ctx.run_stage_qa("responses", responses, rec)
            rec.detail = f"{len(responses.responses)} runs loaded"
        elif category in ("feature_extractors", "feature_sources"):
            fs = outputs["feature"]
            feature_name = adapter.feature_config(module, node.params)["name"]
            source_kind = "compute" if category == "feature_extractors" else module
            fui.feature_info(feature_name, source_kind, n_runs=len(fs.data), n_dims=fs.n_dims)
            rec.detail = f"{feature_name}: {len(fs.data)} runs, {fs.n_dims} dims"
        elif node.type == "utility:bundle_features":
            feature_data = outputs["features"]
            run_ctx.put("features", feature_data)
            run_ctx.dump_intermediate("features", feature_data)
            run_ctx.run_stage_qa("features", feature_data)
            stage.feature_count += len(feature_data.features)
            rec.detail = f"{len(feature_data.features)} feature(s)"
        elif category == "preparers":
            prepared = outputs["prepared"]
            run_ctx.put("prepared", prepared)
            run_ctx.dump_intermediate("prepare", prepared, rec)
            run_ctx.run_stage_qa("prepare", prepared, rec)
            rec.detail = f"train={prepared.X_train.shape[0]} test={prepared.X_test.shape[0]}"
        elif category == "models":
            result = outputs["result"]
            run_ctx.put("result", result)
            run_ctx.dump_intermediate("model", result, rec)
            run_ctx.run_stage_qa("model", result, rec)
            rec.detail = f"mean={result.scores.mean():.4f} max={result.scores.max():.4f}"
        elif category == "analyzers":
            for key, value in outputs.get("context", {}).items():
                if not run_ctx.has(key) or run_ctx._store[key] is not value:
                    run_ctx.put(key, value)
            rec.detail = "ok"
        elif category == "reporters":
            artifacts = outputs.get("artifacts") or {}
            label = module if module not in run_ctx._artifacts else node.id
            run_ctx.add_artifacts(label, artifacts)
            rec.outputs = _relativize(list(artifacts.values()), env.output_dir)
            rec.detail = f"{len(artifacts)} artifact(s)"
        elif node.type == "utility:collect_context":
            rec.detail = f"{len(outputs.get('context', {}))} key(s)"
        else:
            rec.detail = "ok"


def run_subject_config(config: dict, registry: Any, *, write_graph: bool = False,
                       executor: GraphExecutor | None = None) -> PipelineContext:
    """Compile a resolved subject config and run it on the graph engine."""
    executor = executor or GraphExecutor(NodeCatalog(registry).discover())
    return executor.run(compile_subject_config(config), write_graph=write_graph)


def run_subject_stages(config: dict, catalog: NodeCatalog, stages: list[str], context: PipelineContext, *,
                       only_types: set[str] | None = None,
                       executor: GraphExecutor | None = None) -> PipelineContext:
    """Run some stages of a subject config on the graph engine, continuing ``context``.

    Used by a group's subject second pass. The compiled graph is cut down to the
    nodes of ``stages`` (and, with ``only_types``, to those node types), the
    context collector is seeded with ``context``, and what the run produces
    (context keys, artifacts, the run summary) is written back onto ``context``.
    """
    graph = compile_subject_config(config)
    keep = {n.id for n in graph.nodes
            if catalog.stage(n.type) in stages
            and (only_types is None or n.type in only_types or n.type == "utility:collect_context")}
    graph.nodes = [n for n in graph.nodes if n.id in keep]
    graph.edges = [e for e in graph.edges if e.source in keep and e.target in keep]
    graph.stages = [s for s in graph.stages if s in stages]
    seed = ContextValue.from_context(context)
    for node in graph.nodes:
        if node.type == "utility:collect_context":
            node.literal_inputs = {**node.literal_inputs, "seed": seed}
    executor = executor or GraphExecutor(catalog)
    try:
        executor.run(graph)
    finally:
        partial = executor.last_context
        if partial is not None:
            for key, value in partial._store.items():
                if not context.has(key) or context._store[key] is not value:
                    context.put(key, value)
            context._artifacts.update(partial._artifacts)
            if getattr(partial, "run_summary", None) is not None:
                context.run_summary = partial.run_summary
    return context

