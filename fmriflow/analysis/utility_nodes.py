"""Built-in utility nodes with no fixed-stage counterpart."""

from __future__ import annotations

from typing import Any, ClassVar

from fmriflow.analysis.values import CANONICAL_KEYS, ContextValue, merge_contexts
from fmriflow.core.context_keys import resolve_context_key
from fmriflow.core.types import FeatureData


class BundleFeatures:
    """Combine feature spaces, in connection order, into the data one model uses."""

    NODE_TYPE: ClassVar[str] = "utility:bundle_features"
    STAGE: ClassVar[str] = "features"
    PARAM_SCHEMA: ClassVar[dict] = {}
    INPUTS: ClassVar[dict] = {"features": {"type": "FeatureSet", "multiple": True, "required": True,
                                           "description": "Feature spaces; column order follows connection order"}}
    OUTPUTS: ClassVar[dict] = {"features": {"type": "FeatureData"}}

    def run(self, inputs: dict, params: dict, env: Any) -> dict:
        feature_sets = inputs.get("features") or []
        if not isinstance(feature_sets, list):
            feature_sets = [feature_sets]
        bundled: dict = {}
        for fs in feature_sets:
            if fs.name in bundled:
                raise ValueError(f"two feature spaces are both named {fs.name!r}; rename one (feature_name)")
            bundled[fs.name] = fs
        return {"features": FeatureData(features=bundled)}


class CollectContext:
    """Put stage outputs under the context keys context-reading modules expect."""

    NODE_TYPE: ClassVar[str] = "utility:collect_context"
    STAGE: ClassVar[str] = "analyze"
    PARAM_SCHEMA: ClassVar[dict] = {}
    INPUTS: ClassVar[dict] = {
        "seed": {"type": "Context", "required": False, "description": "Starting keys (earlier context)"},
        "stimuli": {"type": "StimulusData", "required": False},
        "responses": {"type": "ResponseData", "required": False},
        "features": {"type": "FeatureData", "required": False},
        "prepared": {"type": "PreparedData", "required": False},
        "result": {"type": "ModelResult", "required": False},
        "bindings": {"type": "Context", "required": False, "description": "Extra keys layered on top"},
    }
    OUTPUTS: ClassVar[dict] = {"context": {"type": "Context"}}

    def run(self, inputs: dict, params: dict, env: Any) -> dict:
        out = merge_contexts(inputs.get("seed"))
        out = out.merged({k: inputs[k] for k in CANONICAL_KEYS if inputs.get(k) is not None})
        if inputs.get("bindings") is not None:
            out = out.merged(inputs["bindings"])
        return {"context": out}


class PickValue:
    """Take one value out of a context by key (``analysis.fsaverage_scores``, ``result.scores``)."""

    NODE_TYPE: ClassVar[str] = "utility:pick"
    STAGE: ClassVar[str] = "analyze"
    PARAM_SCHEMA: ClassVar[dict] = {
        "key": {"type": "string", "required": True, "description": "Context key; dots walk into attributes"},
    }
    INPUTS: ClassVar[dict] = {"context": {"type": "Context", "required": True}}
    OUTPUTS: ClassVar[dict] = {"value": {"type": "any"}}

    @staticmethod
    def validate_params(params: dict) -> list[str]:
        return [] if params.get("key") else ["'key' is required"]

    def run(self, inputs: dict, params: dict, env: Any) -> dict:
        ctx = inputs["context"] if isinstance(inputs.get("context"), ContextValue) else merge_contexts(inputs.get("context"))
        value = resolve_context_key(ctx, params["key"])
        if value is None:
            raise KeyError(f"context has no key {params['key']!r}")
        return {"value": value}


UTILITY_NODES: tuple[type, ...] = (BundleFeatures, CollectContext, PickValue)
