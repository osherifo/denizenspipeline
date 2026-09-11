"""Group and study runs on the graph engine.

:class:`GroupGraphRunner` and :class:`StudyGraphRunner` keep the contracts of
:class:`~fmriflow.group_orchestrator.GroupOrchestrator` and
:class:`~fmriflow.study_orchestrator.StudyOrchestrator`: the same constructor,
``run(resume=...)``, run-directory layout, events, logs and
``group_summary.json`` / ``study_summary.json``. They reuse those classes' stage
driver, so group and study stages keep their names, order and status rules;
what runs inside each stage comes from a group or study graph, compiled from
the config unless one is passed:

- subjects run on the graph engine, one compiled subject graph each, and write
  ``graph.json`` next to their run summary;
- group and study modules each get their own node's params, so two entries of
  the same module no longer share the first entry's params;
- the subject second pass runs each subject's analyze and report stages seeded
  with its context: all of them (``second_pass: legacy``, the default) or only
  the modules marked ``binding_consumer`` (``second_pass: minimal``);
- with ``resume_values: light`` each finished subject saves its model result and
  analysis keys, and a resumed subject brings them back for group analyzers.
"""

from __future__ import annotations

import dataclasses
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from fmriflow import ui as fui
from fmriflow.analysis.adapters import NodeEnv
from fmriflow.analysis.catalog import NodeCatalog
from fmriflow.analysis.compile_legacy import compile_group_config, compile_study_config, compile_subject_config
from fmriflow.analysis.executor import GraphExecutor, _FixedId, run_subject_stages
from fmriflow.analysis.graph import AnalysisGraph
from fmriflow.analysis.persistence import load_light_values, save_light_values
from fmriflow.core.group_types import SubjectResult
from fmriflow.core.log_capture import capture_logs_to
from fmriflow.core.run_summary import NodeRecord
from fmriflow.exceptions import ConfigError
from fmriflow.group_orchestrator import (
    EXTERNAL_PREFIX, GroupOrchestrator, _empty_summary, _load_subject_result_from_disk,
    _merge_second_pass_summary, _subject_already_succeeded, derive_subject_config, resolve_subject_list,
)
from fmriflow.orchestrator import _record, _relativize
from fmriflow.study_orchestrator import StudyOrchestrator, collect_study_groups

logger = logging.getLogger(__name__)


class GroupGraphRunner(GroupOrchestrator):
    """A group run on the graph engine (see the module docstring)."""

    def __init__(self, group_config: dict, registry: Any, run_id: str | None = None, *,
                 graph: AnalysisGraph | None = None, catalog: NodeCatalog | None = None) -> None:
        self.catalog = catalog or NodeCatalog(registry).discover()
        self.graph = graph if graph is not None else compile_group_config(group_config, registry=registry)
        super().__init__(group_config, registry, run_id=run_id)

    # ── graph lookups ───────────────────────────────────────────

    def _module_nodes(self, prefix: str) -> list:
        return [n for n in self.graph.topo_order() if n.type.startswith(prefix)]

    def _map_node(self):
        found = [n for n in self.graph.nodes if n.type == "control:map_subjects"]
        if len(found) != 1:
            raise ConfigError(f"a group graph needs exactly one control:map_subjects node, found {len(found)}")
        return found[0]

    def _env(self, node, globals_: dict | None = None) -> NodeEnv:
        return NodeEnv(node_id=node.id, globals=self.config if globals_ is None else globals_,
                       registry=self.registry, output_dir=str(self.group_dir))

    def _subjects_config(self) -> dict:
        """The group config with the subject fan-out node's values applied."""
        node = self._map_node()
        cfg = dict(self.config)
        for key in ("subjects", "subject_template", "subject_overrides"):
            if node.params.get(key) is not None:
                cfg[key] = node.params[key]
        return cfg

    # ── group_collect + subject fan-out ─────────────────────────

    def _resolve_subject_list(self) -> list[str]:
        return resolve_subject_list(self._subjects_config())

    def _build_subject_configs(self) -> list[dict]:
        cfg = self._subjects_config()
        return [
            derive_subject_config(cfg, subject, output_dir=str(self._subject_output_dir(subject)), validate=True)
            for subject in resolve_subject_list(cfg)
        ]

    def _run_subjects(self, subject_configs: list[dict], resume: bool) -> list[SubjectResult]:
        node = self._map_node()
        max_workers = int(node.params.get("max_workers")
                          or (self.config.get("parallel") or {}).get("max_workers", 4))
        light = self.config.get("resume_values") == "light"
        results: list[SubjectResult | None] = [None] * len(subject_configs)

        def _slot(idx: int, scfg: dict) -> SubjectResult:
            subject = scfg["subject"]
            run_dir = Path(scfg["reporting"]["output_dir"])
            if resume and _subject_already_succeeded(run_dir):
                logger.info("Resume: skipping subject %s (already ok)", subject)
                sr = _load_subject_result_from_disk(subject, scfg, run_dir)
                if light:
                    ctx = load_light_values(scfg, run_dir)
                    if ctx is not None:
                        ctx.run_summary = sr.run_summary
                        sr = dataclasses.replace(sr, context=ctx)
                return sr
            return self._run_one_subject(scfg)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_slot, i, scfg): i for i, scfg in enumerate(subject_configs)}
            for fut in futures:
                results[futures[fut]] = fut.result()
        return [r for r in results if r is not None]

    def _run_one_subject(self, subject_config: dict) -> SubjectResult:
        run_dir = Path(subject_config["reporting"]["output_dir"])
        run_dir.mkdir(parents=True, exist_ok=True)
        subject = subject_config["subject"]
        sub_t0 = time.time()
        fui.emit_event({"event": "group_subject_start", "subject": subject, "group": self.group_name})
        with fui.event_context(subject=subject, group=self.group_name), \
             capture_logs_to(run_dir / "pipeline.log", thread_local=True):
            logger.info("Subject %s (group=%s, run_id=%s) starting", subject, self.group_name, self.run_id)
            graph = compile_subject_config(subject_config)
            executor = GraphExecutor(self.catalog)
            ctx = None
            failed = False
            try:
                ctx = executor.run(graph, write_graph=True)
            except Exception:
                ctx = executor.last_context
                failed = True
                logger.error("Subject %s failed", subject, exc_info=True)
            rs = getattr(ctx, "run_summary", None) if ctx is not None else None
            if rs is None:
                rs = _empty_summary(subject_config)
                if ctx is not None:
                    ctx.run_summary = rs
            try:
                rs.save_json(run_dir / "run_summary.json")
            except Exception:
                logger.warning("Failed to save subject run_summary.json", exc_info=True)
            if not failed and ctx is not None and self.config.get("resume_values") == "light":
                save_light_values(ctx, subject_config, run_dir)
            fui.emit_event({
                "event": "group_subject_done", "subject": subject, "group": self.group_name,
                "status": "failed" if failed else "ok", "elapsed": round(time.time() - sub_t0, 3),
            })
            return SubjectResult(subject=subject, experiment=subject_config.get("experiment", ""),
                                 run_dir=run_dir, run_summary=rs, context=ctx)

    # ── group_analyze ───────────────────────────────────────────

    def _resolve_group_analyzers(self) -> list[tuple[str, object]]:
        return [(n.id, self.catalog.adapter(n.type).instance(self.catalog.module_name(n.type), self._env(n)))
                for n in self._module_nodes("group_analyzer:")]

    def _run_group_analyzers(self, analyzers: list[tuple[str, object]], nodes: list[NodeRecord]) -> None:
        missing = [sr.subject for sr in self.group.subjects if sr.context is None]
        if missing:
            logger.warning(
                "Group analyzers cannot use %d subject(s) without in-memory "
                "results (resumed from disk): %s", len(missing), ", ".join(missing))
        for node_id, ga in analyzers:
            node = self.graph.node(node_id)
            module = self.catalog.module_name(node.type)
            cfg = self.catalog.adapter(node.type).config_for(module, node.params, self._env(node))
            with _record(nodes, _FixedId(node_id), "group_analyzer", module) as rec:
                ga.analyze(self.group, cfg)
                if missing:
                    rec.status = "warning"
                    rec.detail = (
                        f"{len(missing)} subject(s) without in-memory results "
                        f"(resumed from disk) could not contribute: {', '.join(missing)}")
                else:
                    rec.detail = "ok"

    # ── subject second pass ─────────────────────────────────────

    def _second_pass_mode(self) -> str:
        node = next((n for n in self.graph.nodes if n.type == "control:subject_pass"), None)
        return str((node.params.get("mode") if node else None) or self.config.get("second_pass") or "legacy")

    def _binding_consumers(self, subject_config: dict) -> set[str]:
        graph = compile_subject_config(subject_config)
        return {n.type for n in graph.nodes
                if n.type.startswith(("analyzer:", "reporter:")) and self.catalog.has(n.type)
                and getattr(self.catalog.module_class(n.type), "binding_consumer", False)}

    def _rerun_subjects_with_bindings(self, analyzers: list[object]) -> None:
        bindings: dict[str, object] = {}
        for ga in analyzers:
            bindings.update(ga.subject_bindings(self.group) or {})
        if not bindings:
            return
        minimal = self._second_pass_mode() == "minimal"
        for sr in list(self.group.subjects):
            ctx = sr.context
            if ctx is None:
                logger.warning("Skipping second pass for %s: no in-memory context (loaded from disk)", sr.subject)
                continue
            if getattr(ctx, "restored_values", False):
                logger.warning("Skipping second pass for %s: resumed with saved values, not a full context",
                               sr.subject)
                continue
            for key, value in bindings.items():
                ctx.put(f"{EXTERNAL_PREFIX}{key}", value)
            config = sr.run_summary.config_snapshot
            try:
                only = self._binding_consumers(config) if minimal else None
                run_subject_stages(config, self.catalog, ["analyze", "report"], ctx, only_types=only)
            except Exception:
                logger.error("Second pass failed for %s", sr.subject, exc_info=True)
            finally:
                _merge_second_pass_summary(sr, ctx)

    # ── group_report ────────────────────────────────────────────

    def _resolve_group_reporters(self) -> list[tuple[str, object]]:
        return [(n.id, self.catalog.adapter(n.type).instance(self.catalog.module_name(n.type), self._env(n)))
                for n in self._module_nodes("group_reporter:")]

    def _run_group_reporters(self, reporters: list[tuple[str, object]], nodes: list[NodeRecord]) -> None:
        report_cfg = dict(self.config)
        report_cfg["output_dir"] = str(self.group_dir)
        for node_id, gr in reporters:
            node = self.graph.node(node_id)
            module = self.catalog.module_name(node.type)
            cfg = self.catalog.adapter(node.type).config_for(module, node.params, self._env(node, report_cfg))
            with _record(nodes, _FixedId(node_id), "group_reporter", module) as rec:
                artifacts = gr.report(self.group, cfg) or {}
                self.group.put(f"report.{getattr(gr, 'name', module)}", artifacts)
                if isinstance(artifacts, dict):
                    rec.outputs = _relativize([str(v) for v in artifacts.values() if v], str(self.group_dir))
                    rec.detail = f"{len(artifacts)} artifact(s)"


class StudyGraphRunner(StudyOrchestrator):
    """A study run on the graph engine: its groups run as :class:`GroupGraphRunner`."""

    def __init__(self, study_config: dict, registry: Any, run_id: str | None = None,
                 config_path: str | Path | None = None, *,
                 graph: AnalysisGraph | None = None, catalog: NodeCatalog | None = None) -> None:
        self.catalog = catalog or NodeCatalog(registry).discover()
        self.graph = graph if graph is not None else compile_study_config(study_config)
        super().__init__(study_config, registry, run_id=run_id, config_path=config_path)

    def _group_nodes(self) -> list:
        return [n for n in self.graph.nodes if n.type == "control:group"]

    def _module_nodes(self, prefix: str) -> list:
        return [n for n in self.graph.topo_order() if n.type.startswith(prefix)]

    def _env(self, node, globals_: dict | None = None) -> NodeEnv:
        return NodeEnv(node_id=node.id, globals=self.config if globals_ is None else globals_,
                       registry=self.registry, output_dir=str(self.study_dir))

    def _labels_safe(self) -> list[str]:
        return [str(n.params.get("name")) for n in self._group_nodes() if n.params.get("name")]

    def _collect_groups(self) -> list[tuple[str, dict]]:
        entries = [n.params["_entry"] if "_entry" in n.params
                   else {"name": n.params.get("name"), "config": n.params.get("config")}
                   for n in self._group_nodes()]
        return collect_study_groups(entries, self.config_path)

    def _make_group_runner(self, group_config: dict, run_id: str):
        return GroupGraphRunner(group_config, self.registry, run_id=run_id, catalog=self.catalog)

    def _resolve_study_analyzers(self) -> list[tuple[str, object]]:
        return [(n.id, self.catalog.adapter(n.type).instance(self.catalog.module_name(n.type), self._env(n)))
                for n in self._module_nodes("study_analyzer:")]

    def _run_study_analyzers(self, analyzers: list[tuple[str, object]], nodes: list[NodeRecord]) -> None:
        missing = sorted(
            f"{g.study_label or g.group_name}/{sr.subject}"
            for g in self.study.groups for sr in g.subjects
            if sr.context is None
        )
        if missing:
            logger.warning(
                "Study analyzers cannot use %d subject(s) without in-memory "
                "results (resumed from disk): %s", len(missing), ", ".join(missing))
        for node_id, sa in analyzers:
            node = self.graph.node(node_id)
            module = self.catalog.module_name(node.type)
            cfg = self.catalog.adapter(node.type).config_for(module, node.params, self._env(node))
            with _record(nodes, _FixedId(node_id), "study_analyzer", module, isolate=True) as rec:
                try:
                    sa.analyze(self.study, cfg)
                    if missing:
                        rec.status = "warning"
                        rec.detail = (
                            f"{len(missing)} subject(s) without in-memory results "
                            f"(resumed from disk) could not contribute: {', '.join(missing)}")
                    else:
                        rec.detail = "ok"
                except Exception as exc:
                    logger.error("Study analyzer '%s' failed: %s", module, exc, exc_info=True)
                    raise

    def _resolve_study_reporters(self) -> list[tuple[str, object]]:
        return [(n.id, self.catalog.adapter(n.type).instance(self.catalog.module_name(n.type), self._env(n)))
                for n in self._module_nodes("study_reporter:")]

    def _run_study_reporters(self, reporters: list[tuple[str, object]], nodes: list[NodeRecord]) -> None:
        report_cfg = dict(self.config)
        report_cfg["output_dir"] = str(self.study_dir)
        for node_id, sr in reporters:
            node = self.graph.node(node_id)
            module = self.catalog.module_name(node.type)
            cfg = self.catalog.adapter(node.type).config_for(module, node.params, self._env(node, report_cfg))
            with _record(nodes, _FixedId(node_id), "study_reporter", module, isolate=True) as rec:
                try:
                    artifacts = sr.report(self.study, cfg) or {}
                    self.study.put(f"report.{getattr(sr, 'name', module)}", artifacts)
                    if isinstance(artifacts, dict):
                        rec.outputs = _relativize([str(v) for v in artifacts.values() if v], str(self.study_dir))
                        rec.detail = f"{len(artifacts)} artifact(s)"
                except Exception as exc:
                    logger.error("Study reporter '%s' failed: %s", module, exc, exc_info=True)
                    raise
