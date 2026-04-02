# Writing Plugins

Plugins are plain Python classes — no base class required. Implement the right methods, register with a decorator, and the pipeline discovers them automatically.

## Feature extractor

```python
from fmriflow.core.types import FeatureSet, StimulusData
from fmriflow.plugins._decorators import feature_extractor


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
from fmriflow.plugins._decorators import feature_extractor

@feature_extractor("my_feature")
class MyFeatureExtractor:
    ...
```

### Entry points (for packaged plugins)

```toml
# In your plugin's pyproject.toml
[project.entry-points."fmriflow.feature_extractors"]
my_feature = "my_plugin:MyFeatureExtractor"
```

### Web UI

The Plugin Editor in the web UI lets you write, validate, and register plugins directly in the browser. Plugins saved there go to `~/.denizens/plugins/` and are loaded on server startup.

## Plugin types

| Type | Decorator | Required methods |
|------|-----------|-----------------|
| Feature Extractor | `@feature_extractor` | `extract(stimuli, run_names, config)` |
| Preprocessing Step | `@preprocessing_step` | `apply(state, params)` |
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
