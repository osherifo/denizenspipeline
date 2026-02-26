# Configuration Reference

Complete reference for all YAML config parameters in denizenspipeline v2.

---

## Top-level keys

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `experiment` | string | **yes** | — | Experiment name (e.g. `denizens_reading_en`). Used for locating stimuli. |
| `subject` | string | **yes** | — | Subject ID (e.g. `sub01`). |
| `description` | string | no | — | Free-text description of the experiment run. |
| `inherit` | string | no | — | Path to parent YAML config (relative to this file). |
| `checkpoint` | bool | no | `false` | If `true`, save a checkpoint after each stage. |

---

## `subject_config`

Subject-specific metadata used by response loaders and reporters.

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `surface` | string | yes (for response loading) | — | Pycortex surface name (e.g. `sub01fs`). |
| `transform` | string | yes (for response loading) | — | Pycortex transform name (e.g. `sub01fs_default`). |
| `sessions` | list[string] | no | — | Session names for cloud response loading. |
| `description` | string | no | — | Surface description for metadata lookup. |

---

## `paths`

Shared path configuration.

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `data_dir` | string | yes (for `local` response loader) | `.` | Base directory for local data files. Responses are loaded from `{data_dir}/responses/{experiment}/{subject}/`. |
| `s3_bucket` | string | no | `glab-denizens-shared` | S3 bucket name for cloud response loader. |

Supports environment variable substitution: `${DENIZENS_DATA_DIR}`, `${VAR:default}`.

---

## `stimulus`

Controls how stimulus timing data (TextGrids + TRFiles) is loaded.

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `loader` | string | no | `textgrid` | Stimulus loader plugin name. Built-in: `textgrid`, `skip`. |
| `language` | string | no | `en` | Language code. Allowed: `en`, `zh`, `es`. |
| `modality` | string | no | `reading` | Stimulus modality. Allowed: `reading`, `listening`. |
| `sessions` | list[string] | no | `["generic"]` | Session names to load stimuli from. |
| `source` | string | no | `local` | Where to load stimuli. `local` or `cloud`. |
| `textgrid_dir` | string | no | — | Explicit path to directory of `.TextGrid` files. Overrides the default `$DENIZENS_DATA_DIR/stimuli/{experiment}/{session}/TextGrids` convention. |
| `trfile_dir` | string | no | — | Explicit path to directory of `.report` TR files. Overrides the default convention. |
| `n_trs` | dict[str, int] | no | — | Per-run TR counts for synthesizing evenly-spaced trigger times when no `.report` files exist. Keys are run names. |
| `tr` | float | no | `2.0` | TR duration in seconds, used with `n_trs` for synthetic triggers. |

### `skip` loader

Use `loader: skip` when all features are precomputed (loaded from `filesystem`
or `cloud`) and no TextGrid parsing is needed. The features stage will derive
run names from the response data instead.

```yaml
stimulus:
  loader: skip

features:
  - name: gpt2_hidden_states
    source: filesystem
    path: /data/features/gpt2/
    format: npz
```

Note: `source: compute` features require stimuli and will fail validation if
the loader is `skip`.

---

## `response`

Controls how fMRI response data is loaded.

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `loader` | string | no | `cloud` | Response loader plugin. Built-in: `cloud`, `local`. |
| `mask_type` | string | no | `thick` | Pycortex mask type. |
| `multiseries` | string | no | `mean` | How to combine multi-repetition runs. |

### `local` loader

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `path` | string | no | — | Direct path to the directory (or file) containing response files. If set, overrides the `paths.data_dir` convention. |
| `reader` | string | no | `auto` | Response reader strategy. See built-in readers below. |
| `npz_key` | string | no | `data` | Key within `.npz` files (used by `npz_per_run` and `auto` readers). |
| `hdf5_key` | string | no | `data` | Key/prefix within `.hdf5` files (used by `hdf5_per_run`, `single_hdf5`, and `auto` readers). |
| `pickle_key` | string | no | — | Key for nested dict access inside a pickle file (used by `single_pickle` reader). |
| `run_map` | dict | no | — | Rename response runs after loading. Maps reader run names to pipeline run names (must match stimulus/feature names). |

Response directory is resolved as:
1. **`response.path`** if set (use this to point at any directory or file)
2. Otherwise `{paths.data_dir}/responses/{experiment}/{subject}/`

`subject_config.surface` and `subject_config.transform` are used for pycortex mask loading but are optional if pycortex is not installed.

#### Built-in readers

| Reader name | Behavior |
|-------------|----------|
| `auto` | Default. Tries `hdf5_per_run`, then `npz_per_run` (preserves original behavior). |
| `npz_per_run` | One `.npz` file per run (e.g. `story1.npz`). Uses `npz_key` (default `"data"`). |
| `hdf5_per_run` | One `.hdf5` file per run (e.g. `story1.hdf5`). Uses `hdf5_key` (default `"data"`). |
| `single_pickle` | All runs in a single `.pkl` file, dict keyed by run name. Uses `pickle_key` for nested access. |
| `single_hdf5` | All runs in a single `.hdf5` file with one dataset per run. Uses `hdf5_key` as a group prefix. |
| `multiphase_hdf` | multiphase split HDF files: `subject{subject}_{modality}_fmri_data_{phase}.hdf`, each containing story datasets. Handles multi-repetition (3-D) arrays by collapsing across reps. |

#### `multiphase_hdf` reader

For data stored as one HDF file per phase (train/val), with story datasets inside.

**File layout:** `{path}/subject{subject}_{modality}_fmri_data_{phase}.hdf`

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `subject` | string | **yes** | — | Subject identifier (e.g. `"01"`). Used in the filename pattern. |
| `modality` | string | no | `reading` | Modality string in the filename (e.g. `reading`, `listening`). |
| `phases` | list[string] | no | `[trn, val]` | Which phase files to load. |
| `multirep` | string | no | `mean` | How to collapse 3-D arrays `(n_reps, n_trs, n_voxels)`. `mean` averages across reps; `first` takes the first rep. |

```yaml
response:
  loader: local
  reader: multiphase_hdf
  path: /data/responses/
  subject: "01"
  modality: reading
  phases: [trn, val]
```

#### Writing a custom reader

Register a custom reader function to support lab-specific formats:

```python
from denizenspipeline.plugins.response_loaders.readers import response_reader

@response_reader("my_format")
def read_my_format(resp_dir, run_names, config):
    """
    Args:
        resp_dir (Path): Directory or file path from config.
        run_names (list[str] | None): Specific runs to load, or None for all.
        config (dict): The full response config dict.
    Returns:
        dict mapping run_name -> np.ndarray of shape (n_trs, n_voxels).
    """
    # ... your loading logic ...
    return {"run1": array1, "run2": array2}
```

Then reference it in YAML:

```yaml
response:
  loader: local
  reader: my_format
  path: /data/responses/
```

#### Remapping run names with `run_map`

When response files use different names than your stimulus TextGrids, use
`run_map` to translate. Keys are the names the reader produces; values are
the names the rest of the pipeline expects (i.e. the stimulus/feature run names).

This is common when combining data from different sources — for example,
multiphase HDF files store stories as `story_01`–`story_11` while the stimulus
TextGrids are named by story title.

```yaml
response:
  loader: local
  reader: multiphase_hdf
  path: /data/responses/
  subject: "01"
  run_map:
    story_01: story02
    story_02: story11
    story_03: story07
    story_04: story09
    story_05: life
    story_06: story04
    story_07: story08
    story_08: story03
    story_09: story10
    story_10: story05
    story_11: story01

split:
  test_runs: [story01]   # use the mapped names everywhere
```

Any run name **not** in the map is kept as-is, so you only need entries for
names that actually differ.

### `cloud` loader requirements

Uses `paths.s3_bucket`, `subject_config.surface`, `subject_config.transform`, and `subject_config.sessions`. Loads from S3 path `{experiment}/{session}/{run_name}` via cottoncandy.

---

## `features`

A **list** of feature definitions. Each entry declares one feature and where its data comes from.

### Common fields (all sources)

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `name` | string | **yes** | — | Feature name. Also used as extractor name if `extractor` not set. |
| `source` | string | no | `compute` | Where to get feature data. Allowed: `compute`, `filesystem`, `cloud`, `grouped_hdf`. |

### `compute` source

Runs a `FeatureExtractor` plugin against the loaded stimuli.

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `extractor` | string | no | same as `name` | Extractor plugin name (e.g. `bert`, `word2vec`). |
| `params` | dict | no | `{}` | Parameters passed to the extractor's `extract()` and `validate_config()`. |
| `save_to` | dict | no | — | Save extracted features for reuse. See below. |

**`save_to` sub-keys:**

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `backend` | string | **yes** | `filesystem` or `cloud`. |
| `path` | string | yes (filesystem) | Directory to save `.npz` files (one per run). |
| `bucket` | string | yes (cloud) | S3 bucket name. |
| `prefix` | string | no (cloud) | S3 key prefix. |

### `filesystem` source

Loads pre-extracted features from local files.

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `path` | string | **yes** | — | Base directory (for per-run files) or file path (for single pickle). |
| `format` | string | no | `npz` | File format. Allowed: `npz`, `hdf5`, `pickle`. |
| `file_pattern` | string | no | `{run}` | Filename pattern. `{run}` is replaced with the run name. Extension is appended based on format. |
| `npz_key` | string | no | `data` | Key within `.npz` files. |
| `dataset_key` | string | no | `data` | Key within `.hdf5` files. |
| `pickle_key` | string | no | — | Key within a single pickle dict (when path points to a `.pkl` file containing all runs). |
| `layer` | int/string | no | — | Sub-select a layer from nested data (e.g. for multi-layer hidden states stored as dicts). |

### `grouped_hdf` source

Loads features from HDF files where each story is a group containing
datasets per feature: `file.hdf / story_01 / numwords → (n_trs, 1)`.

Ideal for precomputed feature sets split by phase (train/val).

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `paths` | dict or string | **yes** | — | Phase-to-path mapping (e.g. `{trn: path1.hdf, val: path2.hdf}`) or a single path string. |
| `dataset` | string | no | same as `name` | Dataset name within each story group. |
| `run_map` | dict | no | — | Maps HDF story names to pipeline run names (same format as `response.run_map`). |

Use YAML anchors to avoid repeating `paths` and `run_map` for each feature:

```yaml
response:
  run_map: &run_map
    story_01: story02
    story_02: story11
    # ...

_hdf_features: &hdf
  source: grouped_hdf
  paths:
    trn: /data/features/features_trn.hdf
    val: /data/features/features_val.hdf
  run_map: *run_map

features:
  - name: numwords
    <<: *hdf
  - name: english1000
    <<: *hdf
  - name: phonemes
    <<: *hdf
```

### `cloud` source

Loads pre-extracted features from S3 via cottoncandy.

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `bucket` | string | **yes** | — | S3 bucket name. |
| `prefix` | string | no | `""` | S3 key prefix. Arrays are loaded from `{prefix}{run_name}`. |

---

## Built-in feature extractors

All use `source: compute`. The `extractor` name defaults to the feature `name`.

| Extractor name | `n_dims` | Required `params` | Description |
|----------------|----------|-------------------|-------------|
| `numwords` | 1 | — | Word count per TR. |
| `numletters` | 1 | — | Total letter count per TR. |
| `numphonemes` | 1 | — | Phoneme count per TR. |
| `word_length_std` | 1 | — | Std of word lengths per TR. |
| `english1000` | 985 | — | Top-word indicator features. |
| `letters` | 26 | — | Letter frequency histogram per TR. |
| `phonemes` | 39 | — | ARPAbet phoneme histogram per TR. |
| `word2vec` | 300 | `embedding_path` | Word2Vec embeddings (via gensim). |
| `bert` | 768 | — | BERT contextual embeddings (via transformers). |
| `fasttext` | 300 | `model_path` | FastText embeddings. |

### Extractor-specific params

**`word2vec`:**

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `embedding_path` | string | **yes** | Path to gensim KeyedVectors file. |

**`bert`:**

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `model` | string | no | `bert-base-uncased` | Hugging Face model name. |
| `layer` | int | no | `8` | Hidden layer to extract (0-12). |

**`fasttext`:**

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `model_path` | string | **yes** | Path to FastText `.bin` model file. |

---

## `split`

Train/test split configuration.

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `test_runs` | list[string] | **yes** | — | Run names to use for testing. |
| `train_runs` | list[string] / `"auto"` | no | `"auto"` | Run names for training. `"auto"` = all runs not in `test_runs`. |

---

## `preprocessing`

Controls data preparation before model fitting.

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `type` | string | no | `default` | Preprocessor plugin. Built-in: `default`, `pre_prepared`. |
| `trim_start` | int | no | `5` | TRs to trim from the start of each run. |
| `trim_end` | int | no | `5` | TRs to trim from the end of each run. |
| `trim_features` | bool | no | `true` | Apply trimming to features. Set to `false` when features are pre-trimmed (e.g. loaded from `grouped_hdf`). Responses are always trimmed. |
| `delays` | list[int] | no | `[1, 2, 3, 4]` | FIR delays in samples. |
| `zscore` | bool | no | `true` | Z-score features and responses before fitting. |
| `apply_delays` | bool | no | `true` | Apply temporal delays to features. Set to `false` when using `multiple_kernel_ridge` (delays are applied internally per feature group). |

### `pre_prepared` preprocessor

Skips stages 1-4 by loading saved train/test matrices directly.

**Local source** (`source: local`):

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `source` | string | no | `local` or `cloud`. |
| `Y_path` | string | **yes** | Path to `.npz` with `Y_train` and `Y_test` arrays. |
| `X_path` | string | **yes** | Path to `.npz` with `X_train` and `X_test` arrays (or dicts keyed by feature name). |
| `feature_names` | list[string] | no | `[]` | Feature names (needed if X arrays are dicts). |
| `feature_dims` | list[int] | no | `[]` | Dimensions per feature. |
| `delays` | list[int] | no | `[1, 2, 3, 4]` | Delays (metadata only — data is already delayed). |
| `do_zscore` | bool | no | `true` | Z-score Y matrices after loading. |

**Cloud source** (`source: cloud`):

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `s3_bucket` | string | **yes** | S3 bucket name. |
| `Y_train_path` | string | **yes** | S3 key for Y_train array. |
| `Y_test_path` | string | **yes** | S3 key for Y_test array. |
| `X_train_path` | string | **yes** | S3 key for X_train array. |
| `X_test_path` | string | **yes** | S3 key for X_test array. |

---

## `model`

Model fitting configuration.

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `type` | string | no | `bootstrap_ridge` | Model plugin name. Built-in: `bootstrap_ridge`, `himalaya_ridge`, `banded_ridge`, `multiple_kernel_ridge`. |
| `params` | dict | no | `{}` | Model-specific parameters. |

### `bootstrap_ridge` params

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `alphas` | string or list | `"logspace(1,3,20)"` | Ridge regularization values. String `"logspace(start,stop,num)"` is resolved to `np.logspace(...)`. Or pass a list: `[10, 100, 1000]`. |
| `n_boots` | int | `50` | Number of bootstrap iterations for alpha selection. |
| `single_alpha` | bool | `false` | If `true`, use one alpha for all voxels (mean performance). If `false`, per-voxel alpha. |
| `chunk_len` | int | `40` | Length of chunks for bootstrap held-out sampling. |
| `n_chunks` | int | `20` | Number of chunks held out per bootstrap iteration. |

### `himalaya_ridge` params

Cross-validated ridge regression via himalaya. Requires `pip install denizenspipeline[himalaya]`.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `alphas` | string or list | `"logspace(-2,5,20)"` | Regularization values. Same format as `bootstrap_ridge`. |
| `cv` | int | `5` | Number of cross-validation folds. |
| `score_metric` | string | `"r2"` | Scoring metric. `"r2"` or `"pearson_r"`. |
| `force_cpu` | bool | `false` | Force CPU backend (disable GPU acceleration). |

```yaml
model:
  type: himalaya_ridge
  params:
    alphas: logspace(-2,5,20)
    cv: 5
```

### `banded_ridge` params

Banded ridge regression with per-feature-group regularization via himalaya. Automatically computes group labels from `feature_dims` and `delays`. Requires `pip install denizenspipeline[himalaya]`.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `alphas` | string or list | `"logspace(-2,5,20)"` | Regularization values. |
| `cv` | int | `5` | Number of cross-validation folds. |
| `solver_params` | dict | `{}` | Extra parameters passed to the himalaya solver (e.g. `n_iter`). |
| `score_metric` | string | `"r2"` | Scoring metric. `"r2"` or `"pearson_r"`. |
| `force_cpu` | bool | `false` | Force CPU backend. |

Returns `metadata.deltas` (per-group regularization weights) and `metadata.groups` (column group labels).

```yaml
model:
  type: banded_ridge
  params:
    solver_params:
      n_iter: 10
```

### `multiple_kernel_ridge` params

Multiple kernel ridge regression via himalaya. Each feature group gets its own kernel (delays are applied internally per group). **Requires `preprocessing.apply_delays: false`**. Requires `pip install denizenspipeline[himalaya]`.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `alphas` | string or list | `"logspace(-2,5,20)"` | Regularization values. |
| `cv` | int | `5` | Number of cross-validation folds. |
| `solver` | string | `"random_search"` | Himalaya solver name. |
| `n_iter` | int | `200` | Number of solver iterations. |
| `solver_params` | dict | `{}` | Extra solver parameters. |
| `score_metric` | string | `"r2"` | Scoring metric. `"r2"` or `"pearson_r"`. |
| `force_cpu` | bool | `false` | Force CPU backend. |

Returns `metadata.deltas` (per-kernel weights), `metadata.is_dual = true` (weights are dual coefficients, not primal).

```yaml
preprocessing:
  apply_delays: false
  delays: [0, 2, 4, 6, 8, 10, 12, 14, 16, 18]
model:
  type: multiple_kernel_ridge
  params:
    solver: random_search
    n_iter: 200
    cv: 5
```

---

## `reporting`

Controls what output artifacts are generated.

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `formats` | list[string] | no | `["metrics"]` | Reporter plugins to run. Built-in: `metrics`, `weights`, `flatmap`, `histogram`, `webgl`. |
| `output_dir` | string | no | `./results` | Directory for output files. Created automatically. |

Per-reporter options are nested under the reporter name. Each reporter reads its options via `config['reporting'][reporter_name]`.

### Reporter outputs

**`metrics`** — Writes `metrics.json` with:
- `mean_score`, `median_score`, `max_score`: prediction accuracy stats
- `n_voxels`: total voxel count
- `n_significant`: voxels with score > 0.1
- `feature_names`, `feature_dims`, `delays`: model metadata

**`weights`** — Writes `weights.hdf5` (requires `h5py`) with:
- Datasets: `weights` (n_delayed_features, n_voxels), `scores` (n_voxels,), `alphas` (n_voxels,)
- Attributes: `feature_names`, `feature_dims`, `delays`

**`flatmap`** — Writes `prediction_accuracy_flatmap.png` (requires `pycortex`). Uses `cortex.Volume` with mask expansion for volumetric data.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `cmap` | string | `"inferno"` | Matplotlib colormap name. |
| `vmin` | float | `0` | Color scale minimum. |
| `vmax` | float | `0.5` | Color scale maximum. |
| `with_curvature` | bool | `true` | Overlay curvature on flatmap. |
| `threshold` | float \| null | `null` | Mask scores below this value to NaN. |
| `dpi` | int | `100` | PNG resolution. |

**`histogram`** — Writes `score_histogram.png` (requires `matplotlib`). Histogram of per-voxel prediction scores.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `bins` | int | `50` | Number of histogram bins. |
| `threshold` | float \| null | `null` | Draw a vertical reference line at this value. |
| `show_stats` | bool | `true` | Overlay mean, median, and count statistics. |
| `figsize` | list[int] | `[8, 5]` | Figure size `[width, height]` in inches. |
| `dpi` | int | `150` | PNG resolution. |

**`webgl`** — Writes `webgl_viewer/` directory with `index.html` (requires `pycortex`). Interactive 3D brain viewer.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `cmap` | string | `"inferno"` | Matplotlib colormap name. |
| `vmin` | float | `0` | Color scale minimum. |
| `vmax` | float | `0.5` | Color scale maximum. |
| `threshold` | float \| null | `null` | Mask scores below this value to NaN. |
| `open_browser` | bool | `false` | Open the viewer in a browser after generation. |

### Example with per-reporter options

```yaml
reporting:
  formats: [metrics, flatmap, histogram]
  output_dir: ./results/sub01

  flatmap:
    cmap: magma
    vmin: -0.01
    vmax: 0.1
    with_curvature: true
    threshold: null
    dpi: 100

  histogram:
    bins: 50
    threshold: 0.05
    show_stats: true
    figsize: [8, 5]
    dpi: 150
```

---

## Environment variables

Reference in any string value with `${VAR}` or `${VAR:default}`.

| Variable | Purpose | Example |
|----------|---------|---------|
| `DENIZENS_DATA_DIR` | Base data directory | `/data1/experiments/denizens` |
| `DENIZENS_S3_BUCKET` | S3 bucket name | `glab-denizens-shared` |
| `DENIZENS_OUTPUT_DIR` | Default output directory | `~/denizens_results` |

Unset variables without defaults are left as-is (e.g. `${MISSING}` stays `${MISSING}`).

---

## Config inheritance

Any config can inherit from a parent using `inherit`:

```yaml
# child.yaml
inherit: base.yaml   # relative to this file
subject: sub01
preprocessing:
  trim_start: 10      # override just this field
```

Resolution order: `defaults.py` -> parent -> child. Child values override parent values. For dicts, merging is deep (keys are merged). For lists, child replaces parent entirely.

---

## Logging

Every `denizens run` writes a `pipeline.log` file to the configured `output_dir` (default `./results`). This file captures **DEBUG-level** output, including full tracebacks from any reporter or stage failures.

- **Terminal output** is a summary — check the log file for full details.
- The `-v` / `--verbose` flag additionally enables DEBUG output on the terminal.
- On pipeline failure the terminal prints the log file path for quick reference.

Reporter failures are handled gracefully: if one reporter crashes (e.g. pycortex mask issue in `flatmap`), the remaining reporters still run. Failures are logged with full tracebacks. The report stage only fails entirely if **all** reporters fail.

---

## CLI flags

```
denizens run <config> [options]
  --stages STAGES        Comma-separated stage list (e.g. features,preprocess,model)
  --resume-from STAGE    Resume from a saved checkpoint
  --subject SUBJECT      Override the subject field
  --dry-run              Show resolved config without executing
  -v, --verbose          Debug-level logging

denizens validate <config>
  Validate config and check plugin availability without running.

denizens plugins
  List all registered plugins by type.
```

---

## Pipeline stages

Stages run in this order. Use `--stages` to run a subset.

| # | Stage name | Plugin type | Reads from context | Writes to context |
|---|-----------|-------------|-------------------|------------------|
| 1 | `stimuli` | `StimulusLoader` | — | `stimuli` (StimulusData) |
| 2 | `responses` | `ResponseLoader` | — | `responses` (ResponseData) |
| 3 | `features` | `FeatureSource` + `FeatureExtractor` | `stimuli` | `features` (FeatureData) |
| 4 | `preprocess` | `Preprocessor` | `responses`, `features` | `prepared` (PreparedData) |
| 5 | `model` | `Model` | `prepared` | `result` (ModelResult) |
| 6 | `report` | `Reporter` | `result`, `responses` | artifacts (files) |

---

## Full example

```yaml
# experiments/denizens_reading_en_AN.yaml
inherit: base.yaml

experiment: denizens_reading_en
subject: sub01

subject_config:
  sessions: ["session01"]
  surface: sub01fs
  transform: sub01fs_default

stimulus:
  loader: textgrid
  language: en
  modality: reading
  sessions: [generic]

response:
  loader: cloud
  mask_type: thick

features:
  - name: numwords

  - name: english1000

  - name: word2vec
    source: compute
    extractor: word2vec
    params:
      embedding_path: ${DENIZENS_DATA_DIR}/embeddings/word2vec_en.bin
    save_to:
      backend: filesystem
      path: ${DENIZENS_DATA_DIR}/features/word2vec/

  - name: gpt2_hidden_states
    source: filesystem
    path: /data/features/gpt2/
    format: npz

split:
  test_runs: [story01]

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

reporting:
  formats: [metrics, weights]
  output_dir: ./results/sub01
```

## Minimal example

```yaml
experiment: denizens_reading_en
subject: sub01
features:
  - name: numwords
split:
  test_runs: [story01]
```

Everything else uses defaults: `textgrid` stimulus loader, `cloud` response loader, `default` preprocessor (trim 5/5, delays [1,2,3,4], zscore), `bootstrap_ridge` model, `metrics` reporter.
