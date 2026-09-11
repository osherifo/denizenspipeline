# Stage data types

A subject run (`fmriflow run`, `Pipeline.run()`) is a fixed chain of seven stages. Each stage
calls one kind of module and stores the result in the run's **context** under a fixed key. Later
stages read those keys. This page lists what each stage hands to its modules, what it stores, and
the fields of every type.

## The seven stages

| # | Stage | Module type | Method called | Receives | Stores (context key) |
|---|-------|-------------|---------------|----------|----------------------|
| 1 | `stimuli` | Stimulus loader | `load(config)` | the config | `StimulusData` → `stimuli` |
| 2 | `responses` | Response loader | `load(config)` | the config | `ResponseData` → `responses` |
| 3 | `features` | Feature source, or feature extractor for `source: compute` | source: `load(run_names, feature_config)`; extractor: `extract(stimuli, run_names, params)` | run names; extractors also get `StimulusData` | one `FeatureSet` per feature, bundled as `FeatureData` → `features` |
| 4 | `prepare` | Preparer | `prepare(responses, features, config)` | `ResponseData`, `FeatureData` | `PreparedData` → `prepared` |
| 5 | `model` | Model | `fit(prepared, config)` | `PreparedData` | `ModelResult` → `result` |
| 6 | `analyze` | Analyzer | `analyze(context, config)` | the whole context | whatever it puts, by convention `analysis.<name>` |
| 7 | `report` | Reporter | `report(result, context, config)` | `ModelResult` and the context | returns `{label: path}`, collected as the run's artifacts |

Every module also implements `validate_config(config) -> list[str]`. All modules are validated
before the first stage runs, and all errors are reported together.

Notes per stage:

- **features**
    - Run names come from `StimulusData.runs`. When the stimulus loader is `skip`, the stimuli are
      empty and the sorted response run names are used instead.
    - A feature with `source: compute` (the default) runs its extractor on the stimuli.
    - Every other source (`filesystem`, `grouped_hdf`, `cloud`, ...) loads stored matrices by run
      name and never sees the stimuli.
    - The order of the `features:` list is the order in `FeatureData` and of the feature columns in `X`.
- **prepare**
    - `type: pipeline` preparers run their steps on a mutable `PreparationState`: per-run
      dictionaries before the `concatenate` step, train/test matrices after it.
    - That state stays inside the stage; only the final `PreparedData` is stored.
- **analyze**
    - The stage is skipped when `analysis:` is empty.
    - Analyzers run in list order, so each one sees what the earlier ones put.
    - A failing analyzer is logged and the others still run.
- **report**
    - A failing reporter is logged. The stage fails only when every reporter fails.

Per-stage QA reporters (`@qa_reporter(name, stage=...)`) receive the value that stage stores. For
example, `PreparedData` for `prepare` and `ModelResult` for `model`. See [Writing Modules](../guide/modules.md).

## Types

All types live in `fmriflow.core.types` and are frozen dataclasses. Every type has a free-form
`metadata: dict`, where modules can pass extra information downstream (for example a response
loader's per-run split, or a validation mask).

### `StimulusData`

| Field | Type | Description |
|-------|------|-------------|
| `runs` | `dict[str, StimRun]` | One entry per run, keyed by run name |

`StimRun` has `name`, `language` (default `en`), `modality` (`reading`, `listening` or `visual`) and
`stimulus`, which is one of:

| Stimulus | Fields |
|----------|--------|
| `LanguageStim` | `textgrid`, `trfile` (parsed objects); also reachable as `run.textgrid` / `run.trfile` |
| `AudioStim` | `waveform` `(n_samples,)`, `sample_rate`, `tr_times` |
| `VisualStim` | `video_path`, `fps`, `n_frames`, `tr_times` |
| `ImageSeqStim` | `source`, `image_ids` `(n_trials,)`, `source_kind` (`hdf5` or `image_dir`), `dataset` |

### `ResponseData`

| Field | Type | Description |
|-------|------|-------------|
| `responses` | `dict[str, ndarray]` | `(n_trs, n_voxels)` per run |
| `mask` | `ndarray` | Mask that maps voxels back to the volume or surface; `[True]` when the data are already masked |
| `surface` | `str` | pycortex subject used by flatmap reporters |
| `transform` | `str` | pycortex transform used by flatmap reporters |

### `FeatureSet` and `FeatureData`

| Type | Field | Type | Description |
|------|-------|------|-------------|
| `FeatureSet` | `name` | `str` | Feature name |
| | `data` | `dict[str, ndarray]` | `(n_trs, n_dims)` per run |
| | `n_dims` | `int` | Columns per time point |
| `FeatureData` | `features` | `dict[str, FeatureSet]` | All features, in config order; properties `feature_names` and `total_dims` |

### `PreparedData`

| Field | Type | Description |
|-------|------|-------------|
| `X_train`, `X_test` | `ndarray` | `(n_trs, n_delayed_features)` design matrices |
| `Y_train`, `Y_test` | `ndarray` | `(n_trs, n_voxels)` responses |
| `feature_names` | `list[str]` | Feature order in `X` |
| `feature_dims` | `list[int]` | Columns per feature, before delays |
| `delays` | `list[int]` | Delays applied, in TRs |
| `train_runs`, `test_runs` | `list[str]` | Runs in each split |

### `ModelResult`

| Field | Type | Description |
|-------|------|-------------|
| `weights` | `ndarray` | `(n_delayed_features, n_voxels)` |
| `scores` | `ndarray` | `(n_voxels,)` prediction score on the test split |
| `alphas` | `ndarray` | `(n_voxels,)` selected regularisation |
| `feature_names`, `feature_dims`, `delays` | | Copied from `PreparedData`, so weights can be split by feature and delay |

### Analysis results

Analyzers store their results under `analysis.*` keys. Some examples:

| Analyzer | Key | Value |
|----------|-----|-------|
| `variance_partition` | `analysis.variance_partition` | `VariancePartition`: `unique_variance` `(n_groups, n_voxels)`, `shared_variance`, `total_variance`, `group_names` |
| `weight_analysis` | `analysis.weight_analysis` | `WeightAnalysis`: `per_feature_importance` `(n_features, n_voxels)`, `temporal_profiles` `(n_delays, n_features, n_voxels)` |
| `block_permutation_significance` | `output_key`, default `analysis.significance` | dictionary of per-voxel arrays |
| `project_to_fsaverage` | `output_key`, default `analysis.fsaverage_scores` | per-vertex values |

## The context

The context is a `PipelineContext`, which `Pipeline.run()` returns.

- `ctx.put(key, value)` stores a value.
- `ctx.has(key)` checks whether a key is present.
- `ctx.get(key, ExpectedType)` reads a value. It raises `PipelineError` when the key is missing
  ("Was the required stage run?") or when the value has another type.
- `ctx.artifacts` holds the reporters' outputs, as `{reporter: {label: path}}`.

## What is fixed and what you choose

Fixed:

- The seven stages always run in this order, and each stage reads the keys above. A stage fails
  when its input key is missing.
- A run has one stimulus loader, one response loader, one preparer and one model.
- Modules must accept and return the types above; the stages check them with `ctx.get(key, Type)`.

Your choice:

- **The module at every stage.** Use a built-in or your own module registered with a decorator
  (`@response_loader`, `@model`, ...), as long as it keeps the method signature and the return type.
- **How many features, analyzers and reporters.** Analyzers can add new context keys that later
  analyzers and reporters read.
- **Precomputed features.** Skip stimuli with `stimulus: {loader: skip}` and load stored features.
- **Preparation steps**, with `preparation: {type: pipeline, steps: [...]}`.
- **Part of the chain.** Call `Pipeline.run(stages=[...], context=ctx)`. With `checkpoint: true`
  in the config, the context is saved after every stage to
  `<reporting.output_dir>/.checkpoints/<stage>.pkl`. You can then continue with
  `Pipeline.run(stages=["model", "analyze", "report"], resume_from="prepare")`.
