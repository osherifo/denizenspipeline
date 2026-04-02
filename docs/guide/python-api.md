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
    stages=["preprocess", "model", "report"],
    context=ctx,
)
```

## Pipeline stages

| Stage | Plugin type | Input | Output |
|-------|-------------|-------|--------|
| 1. Load Stimuli | `StimulusLoader` | Config | `StimulusData` |
| 2. Load Responses | `ResponseLoader` | Config | `ResponseData` |
| 3. Load/Extract Features | `FeatureSource` + `FeatureExtractor` | `StimulusData` | `FeatureData` |
| 4. Preprocess | `Preprocessor` | `ResponseData` + `FeatureData` | `PreparedData` |
| 5. Fit Model | `Model` | `PreparedData` | `ModelResult` |
| 6. Report | `Reporter` | `ModelResult` | Artifacts (files) |
