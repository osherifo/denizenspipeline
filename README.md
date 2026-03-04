# denizenspipeline v2

Plugin-based pipeline for voxelwise encoding models. Replaces the monolithic v1 `bling` package with a config-driven, modular architecture.

## Install

```bash
cd denizenspipeline
pip install -e .

# With optional dependencies
pip install -e ".[cloud]"    # S3/cottoncandy support
pip install -e ".[viz]"      # pycortex flatmaps
pip install -e ".[nlp]"      # transformers, gensim
pip install -e ".[all]"      # everything
```

## Quickstart

### 1. Write an experiment config

```yaml
# experiments/my_experiment.yaml
experiment: denizens_reading_en
subject: AN

subject_config:
  sessions: ["20170607AN_unwarped"]
  surface: ANfs
  transform: ANfs_default

stimulus:
  language: en
  modality: reading

response:
  loader: cloud

features:
  - name: numwords
  - name: numletters
  - name: english1000
  - name: word2vec
    source: compute
    extractor: word2vec
    params:
      embedding_path: ${DENIZENS_DATA_DIR}/embeddings/word2vec_en.bin

split:
  test_runs: [wheretheressmoke]

reporting:
  formats: [metrics]
  output_dir: ./results/AN
```

### 2. Run it

**CLI:**
```bash
denizens run experiments/my_experiment.yaml
```

**Python:**
```python
from denizenspipeline import Pipeline

pipeline = Pipeline.from_yaml("experiments/my_experiment.yaml")
ctx = pipeline.run()

from denizenspipeline.core.types import ModelResult
result = ctx.get("result", ModelResult)
print(f"Mean prediction accuracy: {result.scores.mean():.4f}")
```

## Minimal example

Only two fields are strictly required beyond `experiment` and `subject` — features and test runs:

```yaml
experiment: moth_reading
subject: CAK
features:
  - name: numwords
  - name: english1000
split:
  test_runs: [wheretheressmoke]
```

Everything else (preprocessing params, model type, response loader, etc.) uses sensible defaults.

## CLI commands

```bash
# Run full pipeline
denizens run experiment.yaml

# Run specific stages
denizens run experiment.yaml --stages features,preprocess,model

# Resume from a checkpoint
denizens run experiment.yaml --resume-from preprocess

# Dry run (show what would execute)
denizens run experiment.yaml --dry-run

# Validate config without running
denizens validate experiment.yaml

# List available plugins
denizens plugins

# List pipeline stages
denizens list

# List all plugins (by category)
denizens list plugins

# List plugins for a specific stage
denizens list preprocess
denizens list features
denizens list model
```

## Python API

```python
from denizenspipeline import Pipeline
from denizenspipeline.core.types import ModelResult, FeatureData

# From YAML
pipeline = Pipeline.from_yaml("experiment.yaml")

# Or from a dict
pipeline = Pipeline(config={
    "experiment": "moth_reading",
    "subject": "CAK",
    "features": [{"name": "numwords"}, {"name": "english1000"}],
    "split": {"test_runs": ["wheretheressmoke"]},
})

# Run everything
ctx = pipeline.run()

# Run stages incrementally (useful in notebooks)
ctx = pipeline.run(stages=["stimuli", "responses", "features"])
features = ctx.get("features", FeatureData)
# inspect features...
ctx = pipeline.run(stages=["preprocess", "model", "report"], context=ctx)
```

## Per-feature source control

Each feature independently declares where its data comes from. This replaces the old `features_to_reload`, `use_presaved_moten`, `Xs_load_method`, etc.

```yaml
features:
  # Compute fresh from stimuli (default)
  - name: numwords
    source: compute

  # Compute and save for future runs
  - name: bert_layer8
    source: compute
    extractor: bert
    params:
      model: bert-base-uncased
      layer: 8
    save_to:
      backend: filesystem
      path: ${DENIZENS_DATA_DIR}/features/bert_layer8/

  # Load pre-extracted features from disk
  - name: gpt2_hidden_states
    source: filesystem
    path: /data/features/gpt2/
    format: npz

  # Load from S3
  - name: shared_bert
    source: cloud
    bucket: glab-denizens-shared
    prefix: features/bert_layer8/
```

## Config inheritance

Configs can inherit from parent configs, so you only specify what changes per subject:

```yaml
# base.yaml
experiment: denizens_reading_en
stimulus:
  language: en
features:
  - name: numwords
  - name: english1000
split:
  test_runs: [wheretheressmoke]
```

```yaml
# subject_AN.yaml
inherit: base.yaml
subject: AN
subject_config:
  sessions: ["20170607AN_unwarped"]
  surface: ANfs
  transform: ANfs_default
```

## Environment variables

Set these to avoid hardcoded paths:

| Variable | Purpose | Example |
|----------|---------|---------|
| `DENIZENS_DATA_DIR` | Base data directory | `/data1/experiments/denizens` |
| `DENIZENS_S3_BUCKET` | S3 bucket name | `glab-denizens-shared` |
| `DENIZENS_OUTPUT_DIR` | Default output directory | `~/denizens_results` |

Reference them in YAML with `${VAR}` or `${VAR:default}`:

```yaml
paths:
  data_dir: ${DENIZENS_DATA_DIR}
  output_dir: ${DENIZENS_OUTPUT_DIR:./results}
```

## Skip to model fitting (pre-prepared data)

If you already have saved X/Y train/test matrices:

```yaml
experiment: precomputed_run
subject: CAK
preprocessing:
  type: pre_prepared
  source: local
  Y_path: /data/COL_en_Y.npz
  X_path: /data/COL_en_Xs.npz
  feature_names: [numwords, motion_energy]
  feature_dims: [1, 2139]
split:
  test_runs: [wheretheressmoke]
```

## Writing a custom plugin

Plugins are plain classes — no base class required, just implement the right methods:

```python
from denizenspipeline.core.types import FeatureSet, StimulusData

class MySurprisalExtractor:
    name = "gpt2_surprisal"
    n_dims = 1

    def extract(self, stimuli: StimulusData, run_names: list[str],
                config: dict) -> FeatureSet:
        # your extraction logic here
        ...

    def validate_config(self, config: dict) -> list[str]:
        return []
```

Register it:

```python
from denizenspipeline.registry import PluginRegistry

registry = PluginRegistry()
registry.discover()

@registry.feature_extractor("gpt2_surprisal")
class MySurprisalExtractor:
    ...
```

Or package it with entry points for automatic discovery:

```toml
# In your plugin's pyproject.toml
[project.entry-points."denizenspipeline.feature_extractors"]
gpt2_surprisal = "my_plugin:MySurprisalExtractor"
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

## Built-in plugins

Run `denizens list plugins` for the full list. Summary:

**Feature Extractors:** `numwords`, `numletters`, `numphonemes`, `word_length_std`, `english1000`, `letters`, `phonemes`, `word2vec`, `bert`, `fasttext`, `gpt2`

**Feature Sources:** `compute`, `filesystem`, `cloud`, `grouped_hdf`

**Stimulus Loaders:** `textgrid`, `skip`

**Response Loaders:** `cloud`, `local`

**Preprocessors:** `default`, `pre_prepared`, `pipeline`

**Preprocessing Steps** (for `type: pipeline`): `split`, `trim`, `zscore`, `concatenate`, `delay`, `mean_center`

**Models:** `bootstrap_ridge`, `himalaya_ridge`, `banded_ridge`, `multiple_kernel_ridge`

**Reporters:** `metrics`, `flatmap`, `weights`, `histogram`, `webgl`

## Defaults

These apply unless overridden in your config:

```yaml
preprocessing:
  trim_start: 5
  trim_end: 5
  delays: [1, 2, 3, 4]
  zscore: true

model:
  type: bootstrap_ridge
  params:
    alphas: logspace(1,3,20)
    n_boots: 50
    single_alpha: false
    chunk_len: 40
    n_chunks: 20

reporting:
  formats: [metrics]
  output_dir: ./results
```
