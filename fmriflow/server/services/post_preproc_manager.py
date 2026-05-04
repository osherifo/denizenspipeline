"""Threaded post-preproc run manager.

v1 runs each graph in a background thread and tracks status in memory.
"""

from __future__ import annotations

import logging
import threading
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fmriflow.post_preproc.manifest import PostPreprocConfig
from fmriflow.post_preproc.runner import run_post_preproc

logger = logging.getLogger(__name__)


@dataclass
class PostPreprocRunHandle:
    run_id: str
    status: str = "pending"  # pending | running | done | failed
    error: str | None = None
    output_dir: str = ""
    manifest: dict[str, Any] | None = None
    config: dict[str, Any] = field(default_factory=dict)


class PostPreprocManager:
    """In-memory tracker for post-preproc runs."""

    def __init__(self):
        self._runs: dict[str, PostPreprocRunHandle] = {}
        self._lock = threading.Lock()
        # Late-bound by app.py so `start_run_from_config_file` can build
        # a runnable config without the caller passing them in.
        self._registry = None
        self._workflow_store = None

    def bind_dependencies(self, *, registry, workflow_store) -> None:
        self._registry = registry
        self._workflow_store = workflow_store

    @property
    def active_runs(self) -> dict[str, PostPreprocRunHandle]:
        """WorkflowManager polls this attribute on every stage manager."""
        return self._runs

    def start(
        self,
        config: PostPreprocConfig,
        registry,
        workflow_store=None,
    ) -> PostPreprocRunHandle:
        run_id = uuid.uuid4().hex[:12]
        handle = PostPreprocRunHandle(
            run_id=run_id,
            status="pending",
            output_dir=str(Path(config.output_dir) / run_id),
            config=config.__dict__,
        )
        with self._lock:
            self._runs[run_id] = handle

        cfg_with_run = PostPreprocConfig(
            subject=config.subject,
            source_manifest_path=config.source_manifest_path,
            graph=config.graph,
            output_dir=handle.output_dir,
            name=config.name,
        )

        thread = threading.Thread(
            target=self._run,
            args=(run_id, cfg_with_run, registry, workflow_store),
            daemon=True,
        )
        thread.start()
        return handle

    def _run(self, run_id: str, config: PostPreprocConfig, registry, workflow_store) -> None:
        with self._lock:
            self._runs[run_id].status = "running"
        try:
            manifest = run_post_preproc(
                config, registry=registry, workflow_store=workflow_store,
            )
            with self._lock:
                handle = self._runs[run_id]
                handle.status = "done"
                handle.manifest = manifest.to_dict()
        except Exception as e:
            logger.exception("post-preproc run %s failed", run_id)
            with self._lock:
                handle = self._runs[run_id]
                handle.status = "failed"
                handle.error = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"

    def get(self, run_id: str) -> PostPreprocRunHandle | None:
        with self._lock:
            return self._runs.get(run_id)

    def list(self) -> list[PostPreprocRunHandle]:
        with self._lock:
            return list(self._runs.values())

    # ── workflow-stage entrypoint ──────────────────────────────────

    def start_run_from_config_file(self, config_path: str) -> str:
        """Run a post-preproc graph described by a stage YAML.

        YAML schema::

            graph: <saved-workflow-name>
            subject: <subject-id>
            source_manifest_path: <path-to-PreprocManifest.json>
            output_dir: <where-to-write>
            bindings:                       # optional
              <wf_input_name>:
                source_run: <run_name>      # take this run's output_file
                # or: path: /abs/path.nii.gz

        Bindings translate the workflow's exposed ``inputs:`` ports into
        concrete files: each key looks up the workflow's declared
        ``inputs[K] = {from: <inner_id>.<inner_handle>}`` and injects a
        literal ``_inputs`` value on that inner node so the runner can
        find the file.
        """
        import copy

        import yaml

        path = Path(config_path)
        if not path.is_file():
            raise FileNotFoundError(f"Post-preproc config not found: {path}")
        data = yaml.safe_load(path.read_text()) or {}
        if not isinstance(data, dict):
            raise ValueError(f"Bad post-preproc config at {path}")

        if self._registry is None or self._workflow_store is None:
            raise RuntimeError(
                "PostPreprocManager.bind_dependencies() not called yet"
            )

        graph_name = data.get("graph")
        if not graph_name:
            raise ValueError(f"{path}: 'graph' is required")
        wf = self._workflow_store.get(graph_name)
        if wf is None:
            raise ValueError(
                f"{path}: saved post-preproc workflow {graph_name!r} not found"
            )

        # Apply bindings into a copy of the inner graph.
        inner_graph = copy.deepcopy(wf.get("graph") or {"nodes": [], "edges": []})
        declared_inputs = wf.get("inputs") or {}
        bindings = data.get("bindings") or {}
        if bindings:
            from fmriflow.preproc.manifest import PreprocManifest
            src_manifest = PreprocManifest.from_json(data["source_manifest_path"])
            for wf_input, binding in bindings.items():
                decl = declared_inputs.get(wf_input)
                if not decl:
                    raise ValueError(
                        f"binding {wf_input!r} not declared by workflow "
                        f"{graph_name!r} (declared: {list(declared_inputs)})"
                    )
                from_str = decl.get("from") if isinstance(decl, dict) else str(decl)
                if not from_str or "." not in from_str:
                    raise ValueError(
                        f"workflow {graph_name!r} input {wf_input!r} has bad "
                        f"target {decl!r}"
                    )
                inner_id, inner_handle = from_str.split(".", 1)
                file_path = self._resolve_binding(binding, src_manifest)
                for node in inner_graph.get("nodes", []):
                    if node.get("id") == inner_id:
                        params = node.setdefault("data", {}).setdefault("params", {})
                        inputs_map = params.setdefault("_inputs", {})
                        inputs_map[inner_handle] = file_path
                        break

        config = PostPreprocConfig(
            subject=data.get("subject", ""),
            source_manifest_path=data["source_manifest_path"],
            graph=inner_graph,
            output_dir=data["output_dir"],
            name=graph_name,
        )
        handle = self.start(
            config, self._registry, workflow_store=self._workflow_store,
        )
        return handle.run_id

    @staticmethod
    def _resolve_binding(binding: dict, src_manifest) -> str:
        if not isinstance(binding, dict):
            raise ValueError(f"binding must be a mapping, got {binding!r}")
        if "path" in binding:
            return str(binding["path"])
        if "source_run" in binding:
            run_name = binding["source_run"]
            for r in src_manifest.runs:
                if r.run_name == run_name:
                    return str(Path(src_manifest.output_dir) / r.output_file)
            raise ValueError(
                f"binding source_run={run_name!r} not in source manifest"
            )
        raise ValueError(f"binding requires 'path' or 'source_run', got {binding!r}")
