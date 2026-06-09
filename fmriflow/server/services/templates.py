"""Module skeleton templates for each category."""

from __future__ import annotations

TEMPLATES: dict[str, str] = {
    'feature_extractors': '''\
"""Custom feature extractor: {name}."""

import numpy as np
from fmriflow.core.types import FeatureSet, StimulusData
from fmriflow.modules._decorators import feature_extractor


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

    'preparation_steps': '''\
"""Custom preparation step: {name}."""

import numpy as np
from fmriflow.core.types import PreparationState
from fmriflow.modules._decorators import preparation_step


@preparation_step("{name}")
class {class_name}:
    name = "{name}"

    PARAM_SCHEMA = {{
        # Add parameters here
    }}

    def apply(self, state: PreparationState, params: dict) -> None:
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
from fmriflow.core.types import ModelResult
from fmriflow.modules._decorators import reporter


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
from fmriflow.core.types import ModelResult
from fmriflow.modules._decorators import analyzer


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
from fmriflow.core.types import StimulusData
from fmriflow.modules._decorators import stimulus_loader


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
from fmriflow.core.types import ResponseData
from fmriflow.modules._decorators import response_loader


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

    'nipype_nodes': '''\
"""Custom post-fmriprep node: {name}."""

from pathlib import Path
from typing import Any

from fmriflow.modules._decorators import nipype_node


@nipype_node("{name}")
class {class_name}:
    """Short description of what this node does."""

    INPUTS = ["in_file"]
    OUTPUTS = ["out_file"]

    PARAM_SCHEMA: dict[str, Any] = {{
        # "fwhm": {{"type": "float", "default": 5.0, "description": "..."}},
    }}

    def run(
        self,
        inputs: dict[str, Path],
        out_dir: Path,
        params: dict[str, Any],
    ) -> dict[str, Path]:
        in_file = Path(inputs["in_file"])
        out_dir.mkdir(parents=True, exist_ok=True)

        # YOUR LOGIC HERE — produce one file per OUTPUTS handle.
        out_path = out_dir / f"{{in_file.stem}}_{name}.nii.gz"

        return {{"out_file": out_path}}
''',

    'qa_reporters': '''\
"""Custom QA reporter: {name} (stage: {stage})."""

from pathlib import Path
from fmriflow.core.types import {value_type}
from fmriflow.modules._decorators import qa_reporter
from fmriflow.modules.qa_reporters._base import (
    ensure_dir, mpl_figure, save_png,
)


@qa_reporter("{name}", stage="{stage}")
class {class_name}:
    """QA reporter for the {stage} stage.

    Receives the {value_type} produced by the {stage} stage; expected
    to write one or more diagnostic artifacts (typically PNGs) into
    ``output_dir`` and return a ``{{key: path}}`` mapping so the
    pipeline summary + QA tab in the UI can find them.
    """

    name = "{name}"
    stage = "{stage}"

    PARAM_SCHEMA: dict = {{
        # Add parameters here. Each key is a config field name; the
        # value is a ``{{'type': ..., 'default': ..., 'description':
        # ...}}`` dict consumed by the param-form auto-renderer.
    }}

    def report(
        self, value: {value_type}, config: dict, output_dir: Path,
    ) -> dict[str, str]:
        ensure_dir(output_dir)

        # YOUR LOGIC HERE.
        # ``value`` is the {value_type} produced by the {stage} stage;
        # ``config`` is the resolved pipeline config dict; pull this
        # reporter's params via ``config.get('qa', {{}}).get(...)``.

        out_path = output_dir / "{name}.png"
        with mpl_figure(figsize=(6, 4)) as fig:
            ax = fig.add_subplot(111)
            ax.set_title("{name}")
            # ax.plot(...)
            save_png(fig, out_path)

        return {{"{name}": str(out_path)}}

    def validate_config(self, config: dict) -> list[str]:
        return []
''',

    'models': '''\
"""Custom model: {name}."""

import numpy as np
from fmriflow.core.types import ModelResult
from fmriflow.modules._decorators import model


@model("{name}")
class {class_name}:
    name = "{name}"

    PARAM_SCHEMA = {{
        # Add parameters here
    }}

    def fit(self, data: PreparedData, config: dict) -> ModelResult:
        params = config.get('model', {{}}).get('params', {{}})

        # YOUR LOGIC HERE
        # data.X_train, data.Y_train: training data
        # data.X_test, data.Y_test: test data
        # Return a ModelResult with scores and weights

        raise NotImplementedError("Implement your model logic here")

    def validate_config(self, config: dict) -> list[str]:
        return []
''',
}


def _to_class_name(module_name: str) -> str:
    """Convert a snake_case module name to PascalCase class name."""
    return ''.join(word.capitalize() for word in module_name.split('_'))


# Stages that accept a QA reporter, mapped to the input type the
# reporter's ``report()`` method receives. Kept in sync with the
# stage→intermediate dataclass mapping the orchestrator uses for
# stage-time QA dispatch (see ``fmriflow/intermediates.py``).
QA_STAGE_VALUE_TYPES: dict[str, str] = {
    'stimuli': 'StimulusData',
    'responses': 'ResponseData',
    'features': 'FeatureData',
    'prepare': 'PreparedData',
    'model': 'ModelResult',
}


def render_template(
    category: str, name: str, *, stage: str | None = None,
) -> str:
    """Return a filled-in template for the given category and name.

    ``stage`` is required for ``qa_reporters`` (the decorator is
    ``@qa_reporter(name, *, stage)``) and ignored for every other
    category.
    """
    if category not in TEMPLATES:
        raise ValueError(f"No template for category '{category}'. "
                         f"Available: {sorted(TEMPLATES.keys())}")
    class_name = _to_class_name(name)
    fmt: dict[str, str] = {'name': name, 'class_name': class_name}
    if category == 'qa_reporters':
        if not stage:
            raise ValueError(
                "qa_reporters template requires a 'stage' parameter. "
                f"One of: {sorted(QA_STAGE_VALUE_TYPES.keys())}")
        if stage not in QA_STAGE_VALUE_TYPES:
            raise ValueError(
                f"Unknown qa_reporter stage '{stage}'. "
                f"One of: {sorted(QA_STAGE_VALUE_TYPES.keys())}")
        fmt['stage'] = stage
        fmt['value_type'] = QA_STAGE_VALUE_TYPES[stage]
    return TEMPLATES[category].format(**fmt)
