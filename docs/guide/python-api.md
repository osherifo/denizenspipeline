# Python API

## Basic usage

```python
from fmriflow import Pipeline
from fmriflow.core.types import ModelResult, FeatureData

# From YAML
pipeline = Pipeline.from_yaml("experiment.yaml")

# Or from a dict
pipeline = Pipeline(config={
    "experiment": "my_experiment",
    "subject": "sub01",
    "features": [{"name": "numwords"}, {"name": "english1000"}],
    "split": {"test_runs": ["story01"]},
})

# Run everything
ctx = pipeline.run()
```

## Accessing results

```python
result = ctx.get("result", ModelResult)
print(f"Mean prediction accuracy: {result.scores.mean():.4f}")
```

## Incremental execution

Run stages independently — useful in notebooks for inspecting intermediate results:

```python
# Run data loading and feature extraction
ctx = pipeline.run(stages=["stimuli", "responses", "features"])

# Inspect features
features = ctx.get("features", FeatureData)

# Continue with model fitting
ctx = pipeline.run(
    stages=["prepare", "model", "report"],
    context=ctx,
)
```

## Pipeline stages

| Stage | Module type | Input | Output (context key) |
|-------|-------------|-------|----------------------|
| 1. `stimuli` | `StimulusLoader` | Config | `StimulusData` (`stimuli`) |
| 2. `responses` | `ResponseLoader` | Config | `ResponseData` (`responses`) |
| 3. `features` | `FeatureSource` / `FeatureExtractor` | Run names (+ `StimulusData` for extractors) | `FeatureData` (`features`) |
| 4. `prepare` | `Preparer` | `ResponseData` + `FeatureData` | `PreparedData` (`prepared`) |
| 5. `model` | `Model` | `PreparedData` | `ModelResult` (`result`) |
| 6. `analyze` | `Analyzer` | The context | New keys, e.g. `analysis.variance_partition` |
| 7. `report` | `Reporter` | `ModelResult` + the context | Artifacts (files) |

See [Stage data types](../reference/stage-data.md) for the fields of each type and what you can change.
