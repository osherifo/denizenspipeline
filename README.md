# fMRIflow

![Version](https://img.shields.io/badge/version-2.0.0--alpha.1-blue)
![Python](https://img.shields.io/badge/python-≥3.10-green)
![License](https://img.shields.io/badge/license-MIT-brightgreen)

Plugin-based pipeline for voxelwise encoding models. Replaces the monolithic v1 `bling` package with a config-driven, modular architecture.

## Install

```bash
cd fmriflow
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
experiment: fmriflow_reading_en
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
      embedding_path: ${FMRIFLOW_DATA_DIR}/embeddings/word2vec_en.bin

split:
  test_runs: [wheretheressmoke]

reporting:
  formats: [metrics]
  output_dir: ./results/AN
```

### 2. Run it

**CLI:**
```bash
fmriflow run experiments/my_experiment.yaml
```

**Python:**
```python
from fmriflow import Pipeline

pipeline = Pipeline.from_yaml("experiments/my_experiment.yaml")
ctx = pipeline.run()

from fmriflow.core.types import ModelResult
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
fmriflow run experiment.yaml

# Run specific stages
fmriflow run experiment.yaml --stages features,preprocess,model

# Resume from a checkpoint
fmriflow run experiment.yaml --resume-from preprocess

# Dry run (show what would execute)
fmriflow run experiment.yaml --dry-run

# Validate config without running
fmriflow validate experiment.yaml

# List available plugins
fmriflow plugins

# List pipeline stages
fmriflow list

# List all plugins (by category)
fmriflow list plugins

# List plugins for a specific stage
fmriflow list preprocess
fmriflow list features
fmriflow list model

# fMRI preprocessing
fmriflow preproc doctor                        # check backend availability
fmriflow preproc collect --backend fmriprep ... # build manifest from existing outputs
fmriflow preproc run --config preproc.yaml      # run preprocessing
fmriflow preproc validate manifest.json         # validate a manifest
fmriflow preproc info manifest.json             # show manifest details
```

## Python API

```python
from fmriflow import Pipeline
from fmriflow.core.types import ModelResult, FeatureData

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
      path: ${FMRIFLOW_DATA_DIR}/features/bert_layer8/

  # Load pre-extracted features from disk
  - name: gpt2_hidden_states
    source: filesystem
    path: /data/features/gpt2/
    format: npz

  # Load from S3
  - name: shared_bert
    source: cloud
    bucket: glab-fmriflow-shared
    prefix: features/bert_layer8/
```

## Config inheritance

Configs can inherit from parent configs, so you only specify what changes per subject:

```yaml
# base.yaml
experiment: fmriflow_reading_en
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
| `FMRIFLOW_DATA_DIR` | Base data directory | `/data1/experiments/fmriflow` |
| `FMRIFLOW_S3_BUCKET` | S3 bucket name | `glab-fmriflow-shared` |
| `FMRIFLOW_OUTPUT_DIR` | Default output directory | `~/fmriflow_results` |

Reference them in YAML with `${VAR}` or `${VAR:default}`:

```yaml
paths:
  data_dir: ${FMRIFLOW_DATA_DIR}
  output_dir: ${FMRIFLOW_OUTPUT_DIR:./results}
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
from fmriflow.core.types import FeatureSet, StimulusData

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
from fmriflow.registry import PluginRegistry

registry = PluginRegistry()
registry.discover()

@registry.feature_extractor("gpt2_surprisal")
class MySurprisalExtractor:
    ...
```

Or package it with entry points for automatic discovery:

```toml
# In your plugin's pyproject.toml
[project.entry-points."fmriflow.feature_extractors"]
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

Run `fmriflow list plugins` for the full list. Summary:

**Feature Extractors:** `numwords`, `numletters`, `numphonemes`, `word_length_std`, `english1000`, `letters`, `phonemes`, `word2vec`, `bert`, `fasttext`, `gpt2`

**Feature Sources:** `compute`, `filesystem`, `cloud`, `grouped_hdf`

**Stimulus Loaders:** `textgrid`, `skip`

**Response Loaders:** `cloud`, `local`, `bids`, `preproc`

**Preprocessors:** `default`, `pre_prepared`, `pipeline`

**Preprocessing Steps** (for `type: pipeline`): `split`, `trim`, `zscore`, `concatenate`, `delay`, `mean_center`

**Models:** `bootstrap_ridge`, `himalaya_ridge`, `banded_ridge`, `multiple_kernel_ridge`

**Reporters:** `metrics`, `flatmap`, `weights`, `histogram`, `webgl`

## fMRI Preprocessing (`fmriflow preproc`)

A standalone module for managing fMRI preprocessing (fmriprep, custom scripts, BIDS-Apps). It produces a `PreprocManifest` — a JSON contract between preprocessing and the analysis pipeline — so you get provenance tracking, validation, and reproducibility.

### Environment setup

fMRIPrep has heavy dependencies, so the recommended approach is to install `fmriflow` into the conda env that already has fmriprep:

```bash
# Option A: install the pipeline into your fmriprep env (recommended)
conda activate fmriprep-py310
cd fmriflow
pip install -e .

# Option B: install fmriprep into the pipeline env
conda activate fmriflow
pip install fmriprep
```

For container-based runs (Singularity), install singularity via conda:

```bash
conda install conda-forge::singularity
```

You also need a FreeSurfer license file. Set it as an environment variable or pass it as a flag:

```bash
export FS_LICENSE=~/fmriprep-local/fs_license.txt
```

### Quick check

```bash
# What backends are available on this machine?
fmriflow preproc doctor
```

### Workflow 1: Register existing fmriprep outputs

If you already ran fmriprep and just want to hook the outputs into the pipeline:

```bash
# Build a manifest from existing fmriprep derivatives
fmriflow preproc collect \
  --backend fmriprep \
  --output-dir /data/derivatives/fmriprep/ \
  --subject AN \
  --task reading \
  --run-map '{"run-01": "alternateithicatom", "run-02": "avatar"}'

# Inspect it
fmriflow preproc info /data/derivatives/fmriprep/sub-AN/preproc_manifest.json

# Validate it (and optionally check compatibility with an analysis config)
fmriflow preproc validate /data/derivatives/fmriprep/sub-AN/preproc_manifest.json
fmriflow preproc validate /data/derivatives/fmriprep/sub-AN/preproc_manifest.json \
  --for-config experiments/fmriflow_reading_en_AN.yaml
```

Then point your analysis config at the manifest:

```yaml
response:
  loader: preproc
  manifest: /data/derivatives/fmriprep/sub-AN/preproc_manifest.json
  mask_type: thick
```

### Workflow 2: Run preprocessing through the pipeline

```bash
# Run fmriprep via Singularity
fmriflow preproc run \
  --backend fmriprep \
  --bids-dir /data/bids/fmriflow_reading/ \
  --output-dir /data/derivatives/fmriprep/ \
  --subject AN \
  --task reading \
  --container /images/fmriprep-23.2.1.sif \
  --container-type singularity \
  --fs-license-file ~/.freesurfer/license.txt \
  --output-spaces T1w MNI152NLin2009cAsym

# Or run from a YAML config
fmriflow preproc run --config preproc_config.yaml
```

A preprocessing YAML config looks like:

```yaml
# preproc_config.yaml
preproc:
  backend: fmriprep
  bids_dir: /data/bids/fmriflow_reading/
  output_dir: /data/derivatives/fmriprep/
  subject: AN
  task: reading
  sessions: [20170607AN]

  backend_params:
    container: /images/fmriprep-23.2.1.sif
    container_type: singularity
    output_spaces: [T1w]
    fs_license_file: ~/.freesurfer/license.txt

  confounds:
    strategy: motion_24
    high_pass: 0.01

  run_map:
    run-01: alternateithicatom
    run-02: avatar
```

### Workflow 3: Custom preprocessing script

```bash
fmriflow preproc run \
  --backend custom \
  --raw-dir /data/raw/AN/ \
  --output-dir /data/preprocessed/AN/ \
  --subject AN \
  --command "python my_preproc.py --subject {subject} --input {input_dir} --output {output_dir}"
```

### Confound regression at load time

Instead of cleaning the data on disk, you can apply confound regression when the analysis pipeline loads the data:

```yaml
response:
  loader: preproc
  manifest: /data/derivatives/fmriprep/sub-AN/preproc_manifest.json
  confounds:
    strategy: motion_24    # or: motion_6, acompcor, custom
    high_pass: 0.01
    fd_threshold: 0.5      # scrub high-motion TRs
```

Available confound strategies:
- `motion_24` — 6 motion params + derivatives + squared + squared derivatives
- `motion_6` — 6 motion params only
- `acompcor` — 6 motion params + 5 anatomical CompCor components
- `custom` — specify exact column names with `columns: [col1, col2, ...]`

### Backends

| Backend | Use case |
|---------|----------|
| `fmriprep` | Wraps fmriprep (bare, Singularity, or Docker) |
| `custom` | Runs any shell command with `{subject}`, `{input_dir}`, `{output_dir}` placeholders |
| `bids_app` | Generic BIDS-App wrapper (any container following the standard CLI) |

### The manifest

The `preproc_manifest.json` records everything about the preprocessing: what backend was used, which version, what parameters, what space, which confounds were applied, per-run QC metrics (framewise displacement, tSNR), and the exact file paths. The analysis pipeline validates this before loading data, so you catch mismatches early instead of getting cryptic shape errors in the model stage.

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
