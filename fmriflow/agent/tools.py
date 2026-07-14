"""Read-only tools the assistant can call to fetch real app context.

Every tool wraps an existing fMRIflow helper and returns JSON-safe data.
Nothing here writes files or mutates state — the assistant is advisory.

A tool is a ``(spec, fn)`` pair: ``spec`` is the Anthropic tool definition
(name + description + JSON-schema input), ``fn(state, **args)`` runs it
against the live ``app.state`` services and returns a JSON-serialisable
result. :func:`run_tool` dispatches by name and always returns a string.
"""

from __future__ import annotations

import dataclasses
import inspect
import json
import logging
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

# name -> (spec dict, callable)
_REGISTRY: dict[str, tuple[dict, Callable[..., Any]]] = {}


def _tool(spec: dict):
    def deco(fn: Callable[..., Any]):
        _REGISTRY[spec["name"]] = (spec, fn)
        return fn
    return deco


def _jsonable(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    if hasattr(obj, "to_dict") and callable(obj.to_dict):
        return obj.to_dict()
    if isinstance(obj, list):
        return [_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    return obj


# ── Configs ──────────────────────────────────────────────────────────

@_tool({
    "name": "list_configs",
    "description": "List all saved analysis pipeline configs (subject/group/study) with summary metadata.",
    "input_schema": {"type": "object", "properties": {}},
})
def _list_configs(state) -> Any:
    return [_jsonable(c) for c in state.config_store.list_configs()]


@_tool({
    "name": "get_config",
    "description": "Get one analysis config by filename — returns both the parsed dict and the raw YAML.",
    "input_schema": {
        "type": "object",
        "properties": {"filename": {"type": "string", "description": "e.g. nsd_subj01_clip.yaml"}},
        "required": ["filename"],
    },
})
def _get_config(state, filename: str) -> Any:
    return state.config_store.get_config(filename) or {"error": f"No config '{filename}'"}


@_tool({
    "name": "list_config_field_values",
    "description": "Unique values seen for each dotted config field across all saved configs (e.g. which models/loaders are in use).",
    "input_schema": {"type": "object", "properties": {}},
})
def _list_config_field_values(state) -> Any:
    return state.config_store.field_values()


# ── Modules / params / stages ────────────────────────────────────────

@_tool({
    "name": "list_modules",
    "description": "List every registered pipeline module (plugin) grouped by category (models, reporters, feature_extractors, ...).",
    "input_schema": {"type": "object", "properties": {}},
})
def _list_modules(state) -> Any:
    return state.registry.list_modules()


@_tool({
    "name": "get_module",
    "description": "Get one module's metadata: docstring, which stage it runs in, and its PARAM_SCHEMA (param names, types, defaults).",
    "input_schema": {
        "type": "object",
        "properties": {
            "category": {"type": "string", "description": "e.g. models, reporters, feature_extractors"},
            "name": {"type": "string"},
        },
        "required": ["category", "name"],
    },
})
def _get_module(state, category: str, name: str) -> Any:
    meta = state.registry.module_metadata().get(category, [])
    for m in meta:
        if m.get("name") == name:
            return m
    return {"error": f"No module '{name}' in category '{category}'"}


@_tool({
    "name": "get_module_source",
    "description": "Read the Python source of a builtin or user module — useful as an example when writing a new one.",
    "input_schema": {
        "type": "object",
        "properties": {"category": {"type": "string"}, "name": {"type": "string"}},
        "required": ["category", "name"],
    },
})
def _get_module_source(state, category: str, name: str) -> Any:
    try:
        cls = state.registry.get_module_class(category, name)
        return {"source": inspect.getsource(cls)}
    except Exception as e:  # noqa: BLE001 - report, don't crash the loop
        return {"error": f"Could not read source for {category}/{name}: {e}"}


@_tool({
    "name": "list_stages",
    "description": "List the pipeline stages (subject 7-stage sequence plus group/study stages) and which module categories fill each.",
    "input_schema": {"type": "object", "properties": {}},
})
def _list_stages(state) -> Any:
    try:
        from fmriflow.server.routes import modules as _m
        return {
            "descriptions": getattr(_m, "STAGE_DESCRIPTIONS", {}),
            "module_categories": getattr(_m, "STAGE_MODULE_CATEGORIES", {}),
        }
    except Exception:  # noqa: BLE001
        from fmriflow.orchestrator import ALL_STAGES
        return {"stages": list(ALL_STAGES)}


# ── Runs / results ───────────────────────────────────────────────────

@_tool({
    "name": "list_runs",
    "description": "List recent pipeline runs (newest first) with per-stage status and timing.",
    "input_schema": {
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "default": 20},
            "experiment": {"type": "string"},
            "subject": {"type": "string"},
        },
    },
})
def _list_runs(state, limit: int = 20, experiment: str | None = None, subject: str | None = None) -> Any:
    runs = state.run_store.list_runs(limit=limit, experiment=experiment, subject=subject)
    return [
        {
            "run_id": r.get("run_id"),
            "output_dir": r.get("output_dir"),
            "summary": _jsonable(r.get("summary")),
        }
        for r in runs
    ]


@_tool({
    "name": "get_run_summary",
    "description": "Get one run's full stage-timing summary by run_id.",
    "input_schema": {
        "type": "object",
        "properties": {"run_id": {"type": "string"}},
        "required": ["run_id"],
    },
})
def _get_run_summary(state, run_id: str) -> Any:
    run = state.run_store.get_run(run_id)
    if not run:
        return {"error": f"No run '{run_id}'"}
    return {
        "run_id": run.get("run_id"),
        "output_dir": run.get("output_dir"),
        "summary": _jsonable(run.get("summary")),
    }


@_tool({
    "name": "get_run_metrics",
    "description": "Read a run's metrics.json (mean/median/max score, n_voxels, n_significant, feature dims).",
    "input_schema": {
        "type": "object",
        "properties": {"run_id": {"type": "string"}},
        "required": ["run_id"],
    },
})
def _get_run_metrics(state, run_id: str) -> Any:
    run = state.run_store.get_run(run_id)
    if not run:
        return {"error": f"No run '{run_id}'"}
    out = run.get("output_dir")
    if not out:
        return {"error": "Run has no output_dir"}
    mp = Path(out) / "metrics.json"
    if not mp.is_file():
        return {"error": f"No metrics.json for run '{run_id}'"}
    try:
        return json.loads(mp.read_text())
    except (OSError, json.JSONDecodeError) as e:
        return {"error": f"Could not read metrics.json: {e}"}


# ── Error KB / triage ────────────────────────────────────────────────

@_tool({
    "name": "search_error_kb",
    "description": "Search the local error knowledge base by free text, stage, and/or tag. Returns matching known-error entries (symptoms, root cause, fix).",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "stage": {"type": "string"},
            "tag": {"type": "string"},
        },
    },
})
def _search_error_kb(state, query: str | None = None, stage: str | None = None, tag: str | None = None) -> Any:
    from fmriflow.server.routes.errors import _scan_errors
    entries = _scan_errors()
    if stage:
        entries = [e for e in entries if e["stage"] == stage]
    if tag:
        entries = [e for e in entries if tag in e["tags"]]
    if query:
        ql = query.lower()
        entries = [
            e for e in entries
            if ql in e["title"].lower()
            or ql in e["symptoms"].lower()
            or ql in e["root_cause"].lower()
            or ql in e["fix"].lower()
            or any(ql in str(t).lower() for t in e["tags"])
        ]
    return entries[:20]


@_tool({
    "name": "get_error_kb_entry",
    "description": "Get one error knowledge-base entry by id.",
    "input_schema": {
        "type": "object",
        "properties": {"id": {"type": "string"}},
        "required": ["id"],
    },
})
def _get_error_kb_entry(state, id: str) -> Any:  # noqa: A002 - matches KB field name
    from fmriflow.server.routes.errors import _scan_errors
    for e in _scan_errors():
        if str(e["id"]) == str(id):
            return e
    return {"error": f"No KB entry '{id}'"}


@_tool({
    "name": "get_triage_for_run",
    "description": "Get the auto-captured triage record for a failed run: symptom, traceback tail, fingerprints, and KB matches.",
    "input_schema": {
        "type": "object",
        "properties": {"run_id": {"type": "string"}},
        "required": ["run_id"],
    },
})
def _get_triage_for_run(state, run_id: str) -> Any:
    from fmriflow.server.services.run_registry import RunRegistry
    from fmriflow.triage.capture import TriageFileName
    path = RunRegistry().run_dir(run_id) / TriageFileName
    if not path.is_file():
        return {"error": f"No triage record for run '{run_id}' (only failed runs have one)."}
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        return {"error": f"Could not read triage.json: {e}"}


# ── Dispatch ─────────────────────────────────────────────────────────

ALL_TOOL_NAMES = list(_REGISTRY.keys())


def specs_for(names: list[str]) -> list[dict]:
    """Return the Anthropic tool specs for the given tool names."""
    return [_REGISTRY[n][0] for n in names if n in _REGISTRY]


def run_tool(name: str, args: dict, state) -> str:
    """Execute a tool and return a JSON string (never raises)."""
    entry = _REGISTRY.get(name)
    if entry is None:
        return json.dumps({"error": f"Unknown tool '{name}'"})
    _, fn = entry
    try:
        result = fn(state, **(args or {}))
        return json.dumps(_jsonable(result), default=str)
    except Exception as e:  # noqa: BLE001 - surface to the model, keep the loop alive
        logger.warning("Agent tool %s failed: %s", name, e)
        return json.dumps({"error": f"Tool '{name}' failed: {e}"})
