"""PipelinePreprocessor — stackable, config-driven preprocessing."""

from __future__ import annotations

import logging

from fmriflow.core.types import (
    FeatureData, PreparedData, PreprocessingState, ResponseData,
)
from fmriflow.plugins._decorators import (
    _preprocessing_steps, preprocessor,
)

logger = logging.getLogger(__name__)


@preprocessor("pipeline")
class PipelinePreprocessor:
    """Chains individually registered preprocessing steps from YAML config.

    Config example::

        preprocessing:
          type: pipeline
          steps:
            - name: split
            - name: trim
              params: {trim_start: 5, trim_end: 5}
            - name: zscore
              params: {targets: [responses, features]}
            - name: concatenate
            - name: delay
              params: {delays: [1, 2, 3, 4]}
    """

    name = "pipeline"
    PARAM_SCHEMA = {
        "steps": {"type": "list[dict]", "required": True, "description": "Ordered list of preprocessing steps ({name, params})"},
    }

    def prepare(self, responses: ResponseData, features: FeatureData,
                config: dict) -> PreparedData:
        prep_cfg = config.get("preprocessing", {})
        steps_cfg = prep_cfg.get("steps", [])

        # Build initial state from raw data
        state = self._build_state(responses, features)

        # Resolve and run each step sequentially
        for step_cfg in steps_cfg:
            step_name = step_cfg["name"]
            params = dict(step_cfg.get("params", {}))
            # Inject full config so steps like split can access config.split
            params["_config"] = config

            step_cls = _preprocessing_steps.get(step_name)
            if step_cls is None:
                raise ValueError(
                    f"Unknown preprocessing step '{step_name}'. "
                    f"Available: {sorted(_preprocessing_steps.keys())}")

            step = step_cls()
            logger.debug("Running preprocessing step: %s", step_name)
            step.apply(state, params)

        return state.to_prepared_data()

    def validate_config(self, config: dict) -> list[str]:
        errors = []
        prep_cfg = config.get("preprocessing", {})
        steps_cfg = prep_cfg.get("steps")

        if steps_cfg is None:
            errors.append(
                "pipeline preprocessor requires 'preprocessing.steps'")
            return errors

        if not isinstance(steps_cfg, list):
            errors.append("'preprocessing.steps' must be a list")
            return errors

        seen_names = []
        for i, step_cfg in enumerate(steps_cfg):
            if not isinstance(step_cfg, dict):
                errors.append(f"preprocessing.steps[{i}] must be a dict")
                continue
            if "name" not in step_cfg:
                errors.append(f"preprocessing.steps[{i}] missing 'name'")
                continue

            step_name = step_cfg["name"]
            seen_names.append(step_name)

            if step_name not in _preprocessing_steps:
                errors.append(
                    f"preprocessing.steps[{i}]: unknown step '{step_name}'. "
                    f"Available: {sorted(_preprocessing_steps.keys())}")
                continue

            # Validate step-specific params
            step = _preprocessing_steps[step_name]()
            step_errors = step.validate_params(step_cfg.get("params", {}))
            errors.extend(step_errors)

        return errors

    @staticmethod
    def _build_state(responses: ResponseData,
                     features: FeatureData) -> PreprocessingState:
        """Build initial PreprocessingState from pipeline stage inputs."""
        # Copy per-run response arrays
        resp_dict = {run: arr.copy()
                     for run, arr in responses.responses.items()}

        # Copy per-run feature arrays, keyed by feature name
        feat_dict: dict[str, dict] = {}
        feature_names = features.feature_names
        feature_dims = []
        for feat_name in feature_names:
            fs = features.features[feat_name]
            feat_dict[feat_name] = {
                run: arr.copy() for run, arr in fs.data.items()}
            feature_dims.append(fs.n_dims)

        return PreprocessingState(
            responses=resp_dict,
            features=feat_dict,
            feature_names=feature_names,
            feature_dims=feature_dims,
        )
