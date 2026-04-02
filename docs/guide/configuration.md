# Configuration

fMRIflow experiments are defined in YAML config files. This page covers the config format, inheritance, and environment variable substitution.

## Config structure

```yaml
experiment: my_reading_study       # experiment name
subject: sub01                     # subject ID

subject_config:                    # subject-specific paths
  sessions: ["session01"]
  surface: sub01_fs
  transform: sub01_default

stimulus:                          # stimulus loading
  language: en
  modality: reading

response:                          # brain response loading
  loader: cloud                    # or: local, bids, preproc

features:                          # feature extraction
  - name: numwords
  - name: english1000
  - name: word2vec
    source: compute
    extractor: word2vec
    params:
      embedding_path: ${FMRIFLOW_DATA_DIR}/embeddings/word2vec_en.bin

preprocessing:                     # data preprocessing (optional)
  trim_start: 5
  trim_end: 5
  delays: [1, 2, 3, 4]
  zscore: true

split:                             # train/test split
  test_runs: [story01]

model:                             # model fitting (optional)
  type: bootstrap_ridge
  params:
    n_boots: 50

reporting:                         # output (optional)
  formats: [metrics]
  output_dir: ./results/sub01
```

Most sections are optional — see [Defaults](../reference/defaults.md) for what applies when omitted.

## Config inheritance

Use `inherit` to build on a base config:

```yaml
# base.yaml
experiment: my_reading_study
stimulus:
  language: en
features:
  - name: numwords
  - name: english1000
split:
  test_runs: [story01]
```

```yaml
# subject_sub01.yaml
inherit: base.yaml
subject: sub01
subject_config:
  sessions: ["session01"]
```

Child configs override parent values. Lists (like `features`) replace the parent list entirely — they don't merge.

## Environment variables

Reference environment variables in YAML with `${VAR}` or `${VAR:default}`:

```yaml
paths:
  data_dir: ${FMRIFLOW_DATA_DIR}
  output_dir: ${FMRIFLOW_OUTPUT_DIR:./results}
```

| Variable | Purpose |
|----------|---------|
| `FMRIFLOW_DATA_DIR` | Base data directory |
| `FMRIFLOW_S3_BUCKET` | S3 bucket name |
| `FMRIFLOW_OUTPUT_DIR` | Default output directory |

## Feature sources

Each feature declares where its data comes from:

| Source | Description |
|--------|-------------|
| `compute` | Extract from stimuli using a `FeatureExtractor` (default) |
| `filesystem` | Load pre-extracted features from disk (npz, npy, hdf5) |
| `cloud` | Load from S3 via cottoncandy |
| `grouped_hdf` | Load from a grouped HDF5 file |

## Validation

Validate a config without running:

```bash
fmriflow validate experiment.yaml
```

This checks: required fields, plugin availability, file paths, parameter types, and split/run consistency.
