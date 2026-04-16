# Writing Modules

Modules are plain Python classes — no base class required. Implement the right methods, register with a decorator, and the pipeline discovers them automatically.

## Feature extractor

```python
from fmriflow.core.types import FeatureSet, StimulusData
from fmriflow.modules._decorators import feature_extractor


@feature_extractor("gpt2_surprisal")
class GPT2SurprisalExtractor:
    name = "gpt2_surprisal"
    n_dims = 1

    PARAM_SCHEMA = {
        "model_name": {
            "type": "str",
            "default": "gpt2",
            "description": "HuggingFace model name",
        },
    }

    def extract(self, stimuli: StimulusData, run_names: list[str],
                config: dict) -> FeatureSet:
        # Your extraction logic here
        ...

    def validate_config(self, config: dict) -> list[str]:
        return []
```

## Registration methods

### Decorator (recommended)

```python
from fmriflow.modules._decorators import feature_extractor

@feature_extractor("my_feature")
class MyFeatureExtractor:
    ...
```

### Entry points (for packaged modules)

```toml
# In your module's pyproject.toml
[project.entry-points."fmriflow.feature_extractors"]
my_feature = "my_module:MyFeatureExtractor"
```

### Web UI

The Module Editor in the web UI lets you write, validate, and register modules directly in the browser. Modules saved there go to `~/.fmriflow/modules/` and are loaded on server startup.

## Module types

| Type | Decorator | Required methods |
|------|-----------|-----------------|
| Feature Extractor | `@feature_extractor` | `extract(stimuli, run_names, config)` |
| Preparation Step | `@preparation_step` | `apply(state, params)` |
| Analyzer | `@analyzer` | `analyze(context, config)` |
| Reporter | `@reporter` | `report(result, context, config)` |
| Stimulus Loader | `@stimulus_loader` | `load(config)` |
| Response Loader | `@response_loader` | `load(config)` |

## PARAM_SCHEMA

Define discoverable parameters with `PARAM_SCHEMA`:

```python
PARAM_SCHEMA = {
    "window_size": {
        "type": "int",
        "default": 5,
        "min": 1,
        "max": 100,
        "description": "Sliding window size in TRs",
    },
    "model_name": {
        "type": "str",
        "default": "bert-base-uncased",
        "enum": ["bert-base-uncased", "bert-large-uncased"],
        "description": "HuggingFace model name",
    },
}
```

The schema is used by the web UI to auto-generate parameter forms and by `validate_config()` for type checking.
