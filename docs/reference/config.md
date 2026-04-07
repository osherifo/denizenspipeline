# Config Reference

Full schema for fMRIflow experiment YAML configs.

## Top-level fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `experiment` | string | yes | Experiment name (used for output paths, logging) |
| `subject` | string | yes | Subject ID |
| `inherit` | string | no | Path to parent config for inheritance |
| `subject_config` | object | no | Subject-specific paths and metadata |
| `stimulus` | object | no | Stimulus loading configuration |
| `response` | object | no | Brain response loading configuration |
| `features` | list | yes | Feature definitions (at least one required) |
| `preprocessing` | object | no | Preprocessing parameters |
| `split` | object | yes | Train/test split definition |
| `model` | object | no | Model type and parameters |
| `reporting` | object | no | Output formats and paths |

## `subject_config`

| Field | Type | Description |
|-------|------|-------------|
| `sessions` | list[str] | Session directory names |
| `surface` | string | FreeSurfer surface name |
| `transform` | string | Transform name |

## `stimulus`

| Field | Type | Description |
|-------|------|-------------|
| `language` | string | Language code (e.g., `en`, `zh`) |
| `modality` | string | Stimulus modality (e.g., `reading`, `listening`) |
| `loader` | string | Stimulus loader plugin name (default: `textgrid`) |

## `response`

| Field | Type | Description |
|-------|------|-------------|
| `loader` | string | Response loader plugin name (`cloud`, `local`, `bids`, `preproc`) |
| `manifest` | string | Path to PreprocManifest (for `preproc` loader) |
| `mask_type` | string | Brain mask type (for `preproc` loader) |
| `confounds` | object | Confound regression settings |

## `features[]`

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Feature name (must match a registered plugin or saved feature) |
| `source` | string | Where to get the data: `compute`, `filesystem`, `cloud`, `grouped_hdf` |
| `extractor` | string | Feature extractor plugin name (for `source: compute`) |
| `params` | object | Extractor-specific parameters |
| `path` | string | Filesystem path (for `source: filesystem`) |
| `format` | string | File format: `npz`, `npy`, `hdf5` |
| `save_to` | object | Save computed features for future reuse |

## `preprocessing`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `type` | string | `default` | Preprocessor plugin: `default`, `pre_prepared`, `pipeline` |
| `trim_start` | int | `5` | TRs to trim from start of each run |
| `trim_end` | int | `5` | TRs to trim from end of each run |
| `delays` | list[int] | `[1,2,3,4]` | FIR delay taps |
| `zscore` | bool | `true` | Z-score normalize per run |

## `split`

| Field | Type | Description |
|-------|------|-------------|
| `test_runs` | list[str] | Run names to hold out for testing |

## `model`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `type` | string | `bootstrap_ridge` | Model plugin name |
| `params` | object | (see defaults) | Model-specific parameters |

## `reporting`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `formats` | list[str] | `[metrics]` | Reporter plugin names |
| `output_dir` | string | `./results` | Output directory |
