"""Assistant modes: per-mode system prompt, tool subset, and context.

Four advisory modes. The frontend picks the mode from the active route
and passes an ``opening context`` payload (current YAML, current module
code, a run_id, ...). :func:`build_opening` formats that payload into the
first user message so the model starts grounded in the user's actual work.
"""

from __future__ import annotations

import json
from typing import Any

from fmriflow.agent import tools

_BASE = (
    "You are an assistant embedded in fMRIflow (the Denizens Pipeline), a modular "
    "fMRI processing and encoding-model platform. Its analysis pipeline runs a fixed "
    "7-stage sequence (stimuli, responses, features, prepare, model, analyze, report), "
    "each stage a registry-resolved plugin chosen by YAML. Use the read-only tools to "
    "ground answers in the user's real configs, modules, runs, and error knowledge base "
    "rather than guessing. You are ADVISORY ONLY: you cannot edit files or run anything — "
    "print YAML or code for the user to copy, and be concise and concrete."
)

_ALL = tools.ALL_TOOL_NAMES

MODES: dict[str, dict] = {
    "pipeline": {
        "label": "Pipeline builder",
        "tools": [
            "list_stages", "list_modules", "get_module",
            "list_config_field_values", "list_configs", "get_config",
        ],
        "system": _BASE + (
            "\n\nMODE: pipeline-building assistant. Help the user design a valid analysis "
            "config. Explain which module fits which stage and what its parameters mean "
            "(check PARAM_SCHEMA via get_module). When you suggest changes, show the exact "
            "YAML snippet to paste into the composer. Point out likely validation problems."
        ),
    },
    "coding": {
        "label": "Coding assistant",
        "tools": ["get_module_source", "get_module", "list_modules", "list_stages"],
        "system": _BASE + (
            "\n\nMODE: module-coding assistant. Help the user author a new pipeline plugin "
            "module in Python. Modules register via decorators, declare a PARAM_SCHEMA dict, "
            "and conform to their category's Protocol. Read an existing sibling module with "
            "get_module_source as a template. Produce complete, copy-pasteable code."
        ),
    },
    "errors": {
        "label": "Error-KB helper",
        "tools": [
            "search_error_kb", "get_error_kb_entry",
            "get_triage_for_run", "get_run_summary",
        ],
        "system": _BASE + (
            "\n\nMODE: error knowledge-base helper. Help the user find the known error that "
            "matches their problem and explain its root cause and fix. If given a failed "
            "run_id, read its triage capture (get_triage_for_run) and connect the symptom "
            "and fingerprints to matching KB entries."
        ),
    },
    "generic": {
        "label": "General helper",
        "tools": _ALL,
        "system": _BASE + (
            "\n\nMODE: general helper. Answer questions about the pipeline, modules, configs, "
            "and results using whichever tools are relevant."
        ),
    },
}

DEFAULT_MODE = "generic"


def resolve(mode: str | None) -> str:
    return mode if mode in MODES else DEFAULT_MODE


def system_prompt(mode: str) -> str:
    return MODES[resolve(mode)]["system"]


def tool_specs(mode: str) -> list[dict]:
    return tools.specs_for(MODES[resolve(mode)]["tools"])


def build_opening(mode: str, context: dict | None) -> str | None:
    """Format the view's opening context into a preamble, or None."""
    if not context:
        return None
    m = resolve(mode)
    parts: list[str] = []
    if m == "pipeline":
        if context.get("yaml"):
            parts.append("The user's current composer config YAML:\n```yaml\n"
                         + str(context["yaml"]).strip() + "\n```")
        if context.get("validationErrors"):
            parts.append("Current validation errors: "
                         + json.dumps(context["validationErrors"]))
    elif m == "coding":
        if context.get("category"):
            parts.append(f"They are authoring a `{context['category']}` module"
                         + (f" for stage `{context['stage']}`." if context.get("stage") else "."))
        if context.get("code"):
            parts.append("Current editor buffer:\n```python\n"
                         + str(context["code"]).strip() + "\n```")
        if context.get("validation"):
            parts.append("Validator output: " + json.dumps(context["validation"]))
    elif m == "errors":
        if context.get("run_id"):
            parts.append(f"They are looking at failed run `{context['run_id']}`.")
        if context.get("error_id"):
            parts.append(f"They are viewing KB entry `{context['error_id']}`.")
    else:
        # generic: pass through any provided free-text context
        if context.get("note"):
            parts.append(str(context["note"]))
    if not parts:
        return None
    return "[Context from the current view]\n" + "\n\n".join(parts)


def mode_list() -> list[dict]:
    """Public list of modes for the frontend/status endpoint."""
    return [{"id": k, "label": v["label"]} for k, v in MODES.items()]
