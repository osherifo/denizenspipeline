"""Category adapters: run fixed-stage modules as graph nodes, unchanged.

Each adapter declares the ports for one module category and calls the
module's existing method (``load``, ``extract``, ``prepare``, ``fit``,
``analyze``, ``report``) with a config synthesised for *this node*: the
graph's globals with only the section the category owns replaced by the
node's params. Two nodes of the same module therefore never see each
other's params, which the name-based lookup of the fixed-stage pipeline
could not guarantee.

Node params are flat, as the module's ``PARAM_SCHEMA`` describes them. The
reserved param ``_section`` holds extra keys for the owned section that are
not module params (kept by configs compiled from the fixed-stage YAML).
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, ClassVar

from fmriflow.analysis.values import ContextValue, merge_contexts
from fmriflow.core.types import FeatureData, ModelResult, StimulusData

logger = logging.getLogger(__name__)

SECTION_PARAM = "_section"

# The value type each stage's QA reporters receive.
QA_STAGE_VALUE_TYPES: dict[str, str] = {
    "stimuli": "StimulusData",
    "responses": "ResponseData",
    "features": "FeatureData",
    "prepare": "PreparedData",
    "model": "ModelResult",
}


@dataclass
class NodeEnv:
    """What a node needs besides its inputs and params."""
    node_id: str
    globals: dict
    registry: Any
    output_dir: str | None = None
    # PipelinePreparer calls this per step: (step_name, elapsed_s, error | None)
    step_callback: Callable[[str, float, BaseException | None], None] | None = None


class NotRunnableYet(NotImplementedError):
    """Raised by node types whose engine support is not available yet."""


def _split_section(params: dict) -> tuple[dict, dict]:
    p = dict(params or {})
    section = p.pop(SECTION_PARAM, None) or {}
    return p, dict(section)


def run_names_for(stimuli: StimulusData | None, responses: Any | None) -> list[str]:
    """Run names from the stimuli, else from the responses (skip-loader configs)."""
    names = list(stimuli.runs.keys()) if stimuli is not None else []
    if not names and responses is not None:
        names = sorted(responses.responses.keys())
    return names


class Adapter:
    """Ports, config synthesis and invocation for one module category."""

    category: ClassVar[str] = ""
    prefix: ClassVar[str] = ""
    stage: ClassVar[str] = ""
    error_policy: ClassVar[str] = "fail"       # "fail" aborts the run; "isolate" marks the node failed
    INPUTS: ClassVar[dict] = {}
    OUTPUTS: ClassVar[dict] = {}
    ADAPTER_PARAMS: ClassVar[dict] = {}        # params the adapter consumes, shown next to the module's
    HIDDEN: ClassVar[frozenset[str]] = frozenset()

    def ports(self, module_cls: type, stage: str | None = None) -> tuple[dict, dict]:
        return copy.deepcopy(self.INPUTS), copy.deepcopy(self.OUTPUTS)

    def params_schema(self, module_cls: type) -> dict:
        schema = dict(getattr(module_cls, "PARAM_SCHEMA", {}) or {})
        schema.update(copy.deepcopy(self.ADAPTER_PARAMS))
        return schema

    def instance(self, name: str, env: NodeEnv, stage: str | None = None) -> Any:
        return env.registry.get_module_class(self.category, name)()

    def config_for(self, name: str, params: dict, env: NodeEnv) -> dict:
        return copy.deepcopy(env.globals)

    def validate(self, name: str, params: dict, env: NodeEnv, stage: str | None = None) -> list[str]:
        inst = self.instance(name, env, stage)
        check = getattr(inst, "validate_config", None)
        return list(check(self.config_for(name, params, env)) or []) if callable(check) else []

    def invoke(self, name: str, inputs: dict, params: dict, env: NodeEnv,
               stage: str | None = None) -> dict[str, Any]:
        raise NotImplementedError


# ── subject scope ────────────────────────────────────────────────────


class StimulusLoaderAdapter(Adapter):
    category = "stimulus_loaders"
    prefix = "stimulus_loader"
    stage = "stimuli"
    OUTPUTS = {"stimuli": {"type": "StimulusData"}}

    def config_for(self, name, params, env):
        p, section = _split_section(params)
        cfg = copy.deepcopy(env.globals)
        cfg["stimulus"] = {**section, **p, "loader": name}
        return cfg

    def invoke(self, name, inputs, params, env, stage=None):
        return {"stimuli": self.instance(name, env).load(self.config_for(name, params, env))}


class ResponseLoaderAdapter(Adapter):
    category = "response_loaders"
    prefix = "response_loader"
    stage = "responses"
    OUTPUTS = {"responses": {"type": "ResponseData"}}

    def config_for(self, name, params, env):
        p, section = _split_section(params)
        cfg = copy.deepcopy(env.globals)
        cfg["response"] = {**section, **p, "loader": name}
        return cfg

    def invoke(self, name, inputs, params, env, stage=None):
        return {"responses": self.instance(name, env).load(self.config_for(name, params, env))}


class FeatureExtractorAdapter(Adapter):
    """A feature extractor, run through the ``compute`` feature source."""

    category = "feature_extractors"
    prefix = "feature_extractor"
    stage = "features"
    INPUTS = {
        "stimuli": {"type": "StimulusData", "required": True},
        "responses": {"type": "ResponseData", "required": False},
    }
    OUTPUTS = {"feature": {"type": "FeatureSet"}}
    ADAPTER_PARAMS = {
        "feature_name": {"type": "string", "default": "",
                         "description": "Name of the feature space (default: the extractor name)"},
        "save_to": {"type": "dict",
                    "description": "Save extracted features for reuse: {backend, path | bucket, prefix}"},
    }

    def feature_config(self, name: str, params: dict) -> dict:
        p, section = _split_section(params)
        feature_name = p.pop("feature_name", "") or section.pop("name", "") or name
        save_to = p.pop("save_to", None) or section.pop("save_to", None)
        cfg = {**section, "name": feature_name, "source": "compute", "extractor": name, "params": p}
        if save_to:
            cfg["save_to"] = save_to
        return cfg

    def _source(self, name: str, env: NodeEnv) -> Any:
        # The registry's compute source (an add-on may replace it); the
        # built-in class when the registry never imported the built-ins.
        try:
            source = env.registry.get_feature_source("compute")
        except Exception:
            from fmriflow.modules.feature_sources.compute import ComputeSource
            source = ComputeSource()
        source.set_extractor(env.registry.get_feature_extractor(name))
        return source

    def instance(self, name, env, stage=None):
        return env.registry.get_feature_extractor(name)

    def validate(self, name, params, env, stage=None):
        return list(self._source(name, env).validate_config(self.feature_config(name, params)) or [])

    def invoke(self, name, inputs, params, env, stage=None):
        stimuli = inputs.get("stimuli")
        source = self._source(name, env)
        source.set_stimuli(stimuli)
        run_names = run_names_for(stimuli, inputs.get("responses"))
        return {"feature": source.load(run_names, self.feature_config(name, params))}


class FeatureSourceAdapter(Adapter):
    category = "feature_sources"
    prefix = "feature_source"
    stage = "features"
    INPUTS = {
        "stimuli": {"type": "StimulusData", "required": False},
        "responses": {"type": "ResponseData", "required": False},
    }
    OUTPUTS = {"feature": {"type": "FeatureSet"}}
    ADAPTER_PARAMS = {
        "feature_name": {"type": "string", "default": "",
                         "description": "Name of the feature space (default: the source name)"},
    }
    # Computing features is the feature_extractor node's job.
    HIDDEN = frozenset({"compute"})

    def feature_config(self, name: str, params: dict) -> dict:
        p, section = _split_section(params)
        feature_name = p.pop("feature_name", "") or section.pop("name", "") or name
        return {**section, **p, "name": feature_name, "source": name}

    def validate(self, name, params, env, stage=None):
        return list(self.instance(name, env).validate_config(self.feature_config(name, params)) or [])

    def invoke(self, name, inputs, params, env, stage=None):
        stimuli, responses = inputs.get("stimuli"), inputs.get("responses")
        if stimuli is None and responses is None:
            raise ValueError("connect stimuli or responses: the run names come from one of them")
        run_names = run_names_for(stimuli, responses)
        return {"feature": self.instance(name, env).load(run_names, self.feature_config(name, params))}


class PreparerAdapter(Adapter):
    category = "preparers"
    prefix = "preparer"
    stage = "prepare"
    INPUTS = {
        "responses": {"type": "ResponseData", "required": True},
        "features": {"type": "FeatureData", "required": True},
    }
    OUTPUTS = {"prepared": {"type": "PreparedData"}}
    ADAPTER_PARAMS = {
        "split": {"type": "dict",
                  "description": "Train/test split, e.g. {test_runs: [...]} (the top-level split: block)"},
    }

    def config_for(self, name, params, env):
        p, section = _split_section(params)
        split = p.pop("split", None)
        cfg = copy.deepcopy(env.globals)
        cfg["preparation"] = {**section, **p, "type": name}
        if split is not None:
            cfg["split"] = split
        return cfg

    def invoke(self, name, inputs, params, env, stage=None):
        inst = self.instance(name, env)
        if env.step_callback is not None:
            inst.on_step = env.step_callback
        prepared = inst.prepare(inputs["responses"], inputs["features"], self.config_for(name, params, env))
        return {"prepared": prepared}


class ModelAdapter(Adapter):
    category = "models"
    prefix = "model"
    stage = "model"
    INPUTS = {"prepared": {"type": "PreparedData", "required": True}}
    OUTPUTS = {"result": {"type": "ModelResult"}}

    def config_for(self, name, params, env):
        p, section = _split_section(params)
        cfg = copy.deepcopy(env.globals)
        cfg["model"] = {**section, "type": name, "params": p}
        return cfg

    def invoke(self, name, inputs, params, env, stage=None):
        return {"result": self.instance(name, env).fit(inputs["prepared"], self.config_for(name, params, env))}


class AnalyzerAdapter(Adapter):
    category = "analyzers"
    prefix = "analyzer"
    stage = "analyze"
    error_policy = "isolate"
    INPUTS = {"context": {"type": "Context", "multiple": True, "required": True}}
    OUTPUTS = {"context": {"type": "Context"}}

    def config_for(self, name, params, env):
        p, section = _split_section(params)
        cfg = copy.deepcopy(env.globals)
        cfg["analysis"] = [{**section, "name": name, "params": p}]
        return cfg

    def invoke(self, name, inputs, params, env, stage=None):
        cfg = self.config_for(name, params, env)
        ctx = merge_contexts(inputs.get("context")).to_context(cfg)
        self.instance(name, env).analyze(ctx, cfg)
        return {"context": ContextValue.from_context(ctx)}


class ReporterAdapter(Adapter):
    category = "reporters"
    prefix = "reporter"
    stage = "report"
    error_policy = "isolate"
    INPUTS = {"context": {"type": "Context", "multiple": True, "required": True}}
    OUTPUTS = {"artifacts": {"type": "Artifacts"}}

    def config_for(self, name, params, env):
        p, section = _split_section(params)
        cfg = copy.deepcopy(env.globals)
        reporting = dict(cfg.get("reporting") or {})
        reporting.update(section)
        reporting["formats"] = [name]
        reporting[name] = p
        if env.output_dir:
            reporting["output_dir"] = env.output_dir
        cfg["reporting"] = reporting
        return cfg

    def invoke(self, name, inputs, params, env, stage=None):
        cfg = self.config_for(name, params, env)
        ctx = merge_contexts(inputs.get("context")).to_context(cfg)
        artifacts = self.instance(name, env).report(ctx.get("result", ModelResult), ctx, cfg) or {}
        return {"artifacts": dict(artifacts)}


class QaReporterAdapter(Adapter):
    category = "qa_reporters"
    prefix = "qa_reporter"
    stage = ""
    error_policy = "isolate"
    OUTPUTS = {"artifacts": {"type": "Artifacts"}}

    def ports(self, module_cls, stage=None):
        value_type = QA_STAGE_VALUE_TYPES.get(stage or "", "any")
        return {"value": {"type": value_type, "required": True}}, copy.deepcopy(self.OUTPUTS)

    def instance(self, name, env, stage=None):
        from fmriflow.modules._decorators import _qa_reporters
        return _qa_reporters[stage][name]()

    def validate(self, name, params, env, stage=None):
        return []

    def invoke(self, name, inputs, params, env, stage=None):
        cfg = copy.deepcopy(env.globals)
        subdir = str((cfg.get("qa") or {}).get("output_subdir", "qa"))
        out_dir = Path(env.output_dir or ".") / subdir / str(stage) / name
        artifacts = self.instance(name, env, stage).report(inputs["value"], cfg, out_dir) or {}
        return {"artifacts": dict(artifacts)}


# ── group and study scope (ports now; execution arrives with fan-out) ──


class _ScopeAdapter(Adapter):
    SECTION: ClassVar[str] = ""

    def config_for(self, name, params, env):
        p, section = _split_section(params)
        cfg = copy.deepcopy(env.globals)
        cfg[self.SECTION] = [{**section, "name": name, "params": p}]
        return cfg

    def invoke(self, name, inputs, params, env, stage=None):
        raise NotRunnableYet(
            f"{self.prefix} nodes run inside group/study graphs, which this engine does not execute yet")


class GroupAnalyzerAdapter(_ScopeAdapter):
    category = "group_analyzers"
    prefix = "group_analyzer"
    stage = "group_analyze"
    SECTION = "group_analyze"
    INPUTS = {"group": {"type": "GroupRun", "required": True}}
    OUTPUTS = {"group": {"type": "GroupRun"}}

    def ports(self, module_cls, stage=None):
        ins, outs = super().ports(module_cls, stage)
        if getattr(module_cls, "produces_subject_artifact", False):
            outs["bindings"] = {"type": "Context",
                                "description": "Values bound into each subject for a follow-up subject pass"}
        return ins, outs


class GroupReporterAdapter(_ScopeAdapter):
    category = "group_reporters"
    prefix = "group_reporter"
    stage = "group_report"
    SECTION = "group_report"
    INPUTS = {"group": {"type": "GroupRun", "required": True}}
    OUTPUTS = {"artifacts": {"type": "Artifacts"}}


class StudyAnalyzerAdapter(_ScopeAdapter):
    category = "study_analyzers"
    prefix = "study_analyzer"
    stage = "study_analyze"
    SECTION = "study_analyze"
    INPUTS = {
        "groups": {"type": "GroupRun", "multiple": True, "required": True},
        "study": {"type": "StudyRun", "required": False},
    }
    OUTPUTS = {"study": {"type": "StudyRun"}}


class StudyReporterAdapter(_ScopeAdapter):
    category = "study_reporters"
    prefix = "study_reporter"
    stage = "study_report"
    SECTION = "study_report"
    INPUTS = {"study": {"type": "StudyRun", "required": True}}
    OUTPUTS = {"artifacts": {"type": "Artifacts"}}


# ── modules that declare their own ports ─────────────────────────────


class NativeAdapter(Adapter):
    """A module (or utility node) with ``INPUTS``, ``OUTPUTS`` and ``run(inputs, params, env)``."""

    def __init__(self, *, category: str, prefix: str, stage: str, error_policy: str = "fail") -> None:
        self.category = category          # type: ignore[misc]
        self.prefix = prefix              # type: ignore[misc]
        self.stage = stage                # type: ignore[misc]
        self.error_policy = error_policy  # type: ignore[misc]

    def ports(self, module_cls, stage=None):
        from fmriflow.graph.ports import normalize_ports
        return (normalize_ports(getattr(module_cls, "INPUTS", None)),
                normalize_ports(getattr(module_cls, "OUTPUTS", None)))

    def params_schema(self, module_cls):
        return dict(getattr(module_cls, "PARAM_SCHEMA", {}) or {})

    def instance(self, name, env, stage=None):
        return self._cls()

    def bind(self, module_cls: type) -> NativeAdapter:
        self._cls = module_cls
        return self

    def validate(self, name, params, env, stage=None):
        check = getattr(self._cls, "validate_params", None)
        return list(check(params) or []) if callable(check) else []

    def invoke(self, name, inputs, params, env, stage=None):
        return dict(self.instance(name, env).run(inputs, dict(params or {}), env) or {})


def is_native(module_cls: type) -> bool:
    return (callable(getattr(module_cls, "run", None))
            and getattr(module_cls, "INPUTS", None) is not None
            and getattr(module_cls, "OUTPUTS", None) is not None)


CATEGORY_ADAPTERS: dict[str, Adapter] = {a.category: a for a in (
    StimulusLoaderAdapter(), ResponseLoaderAdapter(), FeatureExtractorAdapter(), FeatureSourceAdapter(),
    PreparerAdapter(), ModelAdapter(), AnalyzerAdapter(), ReporterAdapter(), QaReporterAdapter(),
    GroupAnalyzerAdapter(), GroupReporterAdapter(), StudyAnalyzerAdapter(), StudyReporterAdapter(),
)}

# The first-pass feature bundling needs FeatureData, re-exported for utility nodes.
__all__ = ["Adapter", "CATEGORY_ADAPTERS", "FeatureData", "NativeAdapter", "NodeEnv",
           "NotRunnableYet", "QA_STAGE_VALUE_TYPES", "SECTION_PARAM", "is_native", "run_names_for"]
