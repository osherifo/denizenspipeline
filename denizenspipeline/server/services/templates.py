"""Plugin skeleton templates for each category."""

from __future__ import annotations

TEMPLATES: dict[str, str] = {
    'feature_extractors': '''\
"""Custom feature extractor: {name}."""

import numpy as np
from denizenspipeline.core.types import FeatureSet, StimulusData
from denizenspipeline.plugins._decorators import feature_extractor


@feature_extractor("{name}")
class {class_name}:
    name = "{name}"
    n_dims = 1

    PARAM_SCHEMA = {{
        # Add parameters here, e.g.:
        # "window_size": {{
        #     "type": "int",
        #     "default": 5,
        #     "min": 1,
        #     "description": "Sliding window size in TRs",
        # }},
    }}

    def extract(self, stimuli: StimulusData, run_names: list[str],
                config: dict) -> FeatureSet:
        params = config.get('params', {{}})
        data = {{}}

        for run_name in run_names:
            stim_run = stimuli.runs[run_name]
            n_trs = len(stim_run.trfile.trtimes) if stim_run.trfile else 100

            # YOUR LOGIC HERE
            # Compute a (n_trs, self.n_dims) array for this run
            features = np.zeros((n_trs, self.n_dims))

            data[run_name] = features

        return FeatureSet(name=self.name, data=data, n_dims=self.n_dims)

    def validate_config(self, config: dict) -> list[str]:
        return []
''',

    'preprocessing_steps': '''\
"""Custom preprocessing step: {name}."""

import numpy as np
from denizenspipeline.core.types import PreprocessingState
from denizenspipeline.plugins._decorators import preprocessing_step


@preprocessing_step("{name}")
class {class_name}:
    name = "{name}"

    PARAM_SCHEMA = {{
        # Add parameters here
    }}

    def apply(self, state: PreprocessingState, params: dict) -> None:
        # state.responses: dict[run_name -> np.ndarray]  (before concatenation)
        # state.features: dict[feat_name -> dict[run_name -> np.ndarray]]
        # state.X_train, state.Y_train, etc.  (after concatenation)

        if state.is_concatenated:
            # Operate on concatenated matrices
            # YOUR LOGIC HERE
            pass
        else:
            # Operate on per-run dicts
            for run_name, arr in state.responses.items():
                # YOUR LOGIC HERE
                state.responses[run_name] = arr

    def validate_params(self, params: dict) -> list[str]:
        return []
''',

    'reporters': '''\
"""Custom reporter: {name}."""

import json
from pathlib import Path
from denizenspipeline.core.types import ModelResult
from denizenspipeline.plugins._decorators import reporter


@reporter("{name}")
class {class_name}:
    name = "{name}"

    PARAM_SCHEMA = {{
        # Add parameters here
    }}

    def report(self, result: ModelResult, context, config: dict) -> dict[str, str]:
        output_dir = Path(config.get('reporting', {{}}).get('output_dir', './results'))
        output_dir.mkdir(parents=True, exist_ok=True)

        # YOUR LOGIC HERE
        # result.scores: (n_voxels,) prediction correlations
        # result.weights: (n_delayed_features, n_voxels) model weights
        # result.feature_names, result.feature_dims, result.delays

        output_path = output_dir / '{name}_output.json'
        output_path.write_text(json.dumps({{"placeholder": True}}, indent=2))

        return {{'output': str(output_path)}}

    def validate_config(self, config: dict) -> list[str]:
        return []
''',

    'analyzers': '''\
"""Custom analyzer: {name}."""

import numpy as np
from denizenspipeline.core.types import ModelResult
from denizenspipeline.plugins._decorators import analyzer


@analyzer("{name}")
class {class_name}:
    name = "{name}"

    PARAM_SCHEMA = {{
        # Add parameters here
    }}

    def analyze(self, context, config: dict) -> None:
        result = context.get('result', ModelResult)

        # Find this analyzer's config
        params = {{}}
        for acfg in config.get('analysis', []):
            if acfg.get('name') == self.name:
                params = acfg.get('params', {{}})
                break

        # YOUR LOGIC HERE
        # Read from context, compute results, store back:
        # context.put('analysis.{name}', your_result)

    def validate_config(self, config: dict) -> list[str]:
        return []
''',

    'stimulus_loaders': '''\
"""Custom stimulus loader: {name}."""

from pathlib import Path
from denizenspipeline.core.types import StimulusData
from denizenspipeline.plugins._decorators import stimulus_loader


@stimulus_loader("{name}")
class {class_name}:
    name = "{name}"

    PARAM_SCHEMA = {{
        # Add parameters here
    }}

    def load(self, config: dict, context) -> StimulusData:
        # YOUR LOGIC HERE
        # Return a StimulusData object
        raise NotImplementedError("Implement your stimulus loading logic here")

    def validate_config(self, config: dict) -> list[str]:
        return []
''',

    'response_loaders': '''\
"""Custom response loader: {name}."""

from pathlib import Path
from denizenspipeline.core.types import ResponseData
from denizenspipeline.plugins._decorators import response_loader


@response_loader("{name}")
class {class_name}:
    name = "{name}"

    PARAM_SCHEMA = {{
        # Add parameters here
    }}

    def load(self, config: dict, context) -> ResponseData:
        # YOUR LOGIC HERE
        # Return a ResponseData object
        raise NotImplementedError("Implement your response loading logic here")

    def validate_config(self, config: dict) -> list[str]:
        return []
''',

    'models': '''\
"""Custom model: {name}."""

import numpy as np
from denizenspipeline.core.types import ModelResult
from denizenspipeline.plugins._decorators import model


@model("{name}")
class {class_name}:
    name = "{name}"

    PARAM_SCHEMA = {{
        # Add parameters here
    }}

    def fit_predict(self, X_train, Y_train, X_test, Y_test, config: dict) -> ModelResult:
        params = config.get('model', {{}}).get('params', {{}})

        # YOUR LOGIC HERE
        # X_train, Y_train: training data
        # X_test, Y_test: test data
        # Return a ModelResult with scores and weights

        raise NotImplementedError("Implement your model logic here")

    def validate_config(self, config: dict) -> list[str]:
        return []
''',
}


def _to_class_name(plugin_name: str) -> str:
    """Convert a snake_case plugin name to PascalCase class name."""
    return ''.join(word.capitalize() for word in plugin_name.split('_'))


def render_template(category: str, name: str) -> str:
    """Return a filled-in template for the given category and name."""
    if category not in TEMPLATES:
        raise ValueError(f"No template for category '{category}'. "
                         f"Available: {sorted(TEMPLATES.keys())}")
    class_name = _to_class_name(name)
    return TEMPLATES[category].format(name=name, class_name=class_name)
