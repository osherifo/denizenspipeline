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

preparation:                       # analysis-stage data prep (optional)
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
| `npz_concat` | Pre-trimmed pre-concatenated `.npz` files (one per-run-stacked array per phase) |

### `npz_concat`

For datasets where one `.npz` holds every training run's features
concatenated along time (and another holds validation), with per-run
boundaries implicit. Splits back into per-run blocks via an explicit
ordered length map:

```yaml
features:
  - name: moten
    source: npz_concat
    path: /data/.../motion_energy.npz
    train:
      key: moten_Rstim                # 2-D (T_concat, D)
      runs:                           # ordered: npz-side name → row count
        story_01: 343
        story_02: 367
        # …
    val:
      key: moten_Pstim                # 2-D, or 3-D (k_reps, T, D) collapsed
      repeat: 0                       # int index or 'mean'
      runs:
        story_11: 291
    run_map:                          # optional npz-name → pipeline-name
      story_01: alternateithicatom
      # …
```

The lengths must sum to the array's row count; the loader rejects
mis-declared maps before any modelling happens.

## Intermediate outputs

Opt-in: dump each subject-pipeline stage's resolved dataclass to
`<run_dir>/intermediates/` so QA can re-render plots later without
rerunning the model. Top-level on a subject config (or on a group /
study config, where it propagates into every subject):

```yaml
intermediates:
  save: [prepare, model]          # subset of stimuli/responses/features/prepare/model
  compress: lz4                   # 'lz4' (falls back to gzip when lz4 missing) | 'gzip' | 'none' | int
  format: joblib                  # only joblib in v1
```

`save: true` expands to every saveable stage. The on-disk path is
`<run_dir>/intermediates/<stage>.joblib[.lz4|.gz]`.

## QA visualization

Per-stage diagnostic plots, registered as `@qa_reporter` plugins.
Same propagation rules as `intermediates:` — set on the highest scope
and per-subject overrides win.

```yaml
qa:
  enabled: true
  stages: [responses, features, prepare, model]      # subset of the saveable stages
  responses:
    voxel_carpet:
      max_voxels: null                       # plot every voxel
  features:
    feature_matrix:
      max_dims_per_feature: null             # show every dim, even moten's 6555
  prepare:
    responses_features_alignment:
      max_voxels: 1500
```

Each plugin lands its PNG (+ a JSON sidecar) under
`<run_dir>/<subject>/qa/<stage>/`. In the web UI, every stage node in
the graph viewer has a QA tab with the rendered files and a
**Regenerate** button — that hits a backend endpoint which reloads
the saved intermediate (if present) and re-runs only the QA plugins,
no need to rerun the model.

## Per-feature trim override

The `trim` preparation step accepts a `per_feature:` map so individual
features can opt out of (or override) the global trim. Use case:
motion energy loaded from a pre-trimmed `npz_concat` needs to skip the
global feature trim while the other features still get cut:

```yaml
preparation:
  type: pipeline
  steps:
    - {name: split}
    - {name: trim, params: {trim_start: 10, trim_end: 10, targets: [responses]}}
    - name: trim
      params:
        trim_start: 10
        trim_end: 5
        targets: [features]
        per_feature:
          moten: {trim_start: 0, trim_end: 0}   # already pre-trimmed
    - {name: zscore}
    - {name: concatenate}
```

## Validation

Validate a config without running:

```bash
fmriflow validate experiment.yaml
```

This checks: required fields, module availability, file paths, parameter types, and split/run consistency.
