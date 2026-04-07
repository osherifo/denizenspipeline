# Quickstart

## Write an experiment config

```yaml
# experiments/my_experiment.yaml
experiment: my_reading_study
subject: sub01

subject_config:
  sessions: ["session01"]
  surface: sub01_fs
  transform: sub01_default

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
  test_runs: [story01]

reporting:
  formats: [metrics]
  output_dir: ./results/sub01
```

## Run it

```bash
fmriflow run experiments/my_experiment.yaml
```

## Minimal example

Only two fields are strictly required beyond `experiment` and `subject` — features and test runs:

```yaml
experiment: my_experiment
subject: sub01
features:
  - name: numwords
  - name: english1000
split:
  test_runs: [story01]
```

Everything else (preprocessing params, model type, response loader, etc.) uses sensible defaults.

## Config inheritance

Configs can inherit from parent configs, so you only specify what changes per subject:

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
  surface: sub01_fs
  transform: sub01_default
```

## Per-feature source control

Each feature independently declares where its data comes from:

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
    bucket: my-shared-bucket
    prefix: features/bert_layer8/
```

## Skip to model fitting

If you already have saved X/Y train/test matrices:

```yaml
experiment: precomputed_run
subject: sub01
preprocessing:
  type: pre_prepared
  source: local
  Y_path: /data/sub01_Y.npz
  X_path: /data/sub01_Xs.npz
  feature_names: [numwords, motion_energy]
  feature_dims: [1, 2139]
split:
  test_runs: [story01]
```
