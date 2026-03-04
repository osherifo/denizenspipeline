# Plan: Stackable Preprocessing Pipeline

## Context

The current `DefaultPreprocessor` is monolithic — it hardcodes trim -> zscore -> concatenate -> delay in a single `prepare()` method. Users cannot insert, reorder, or compose custom steps (e.g., z-score -> filtering -> stepwise regression). This plan adds a `type: pipeline` preprocessor that chains individually registered steps specified in YAML config, while keeping `type: default` fully backward-compatible.

## YAML Config

Existing configs work unchanged. New stackable config:

```yaml
preprocessing:
  type: pipeline
  steps:
    - name: split
    - name: trim
      params: {trim_start: 5, trim_end: 5}
    - name: zscore
      params: {targets: [responses, features]}
    - name: concatenate
    - name: delay
      params: {delays: [1, 2, 3, 4]}
```

## Key Design Decisions

- **`PreprocessingState`** — mutable dataclass that holds per-run dicts (before concatenation) AND concatenated matrices (after). Steps mutate it in place. Only lives inside the preprocessing stage — not part of the public inter-stage protocol.
- **`PreprocessingStep`** — new Protocol (`name`, `apply(state, params)`, `validate_params(params)`)
- **`PipelinePreprocessor`** — new `@preprocessor("pipeline")` that builds initial state, resolves steps from config, runs them sequentially, converts to `PreparedData`
- **No orchestrator changes** — `PipelinePreprocessor` satisfies the existing `Preprocessor` protocol

## Implementation Steps

### 1. `core/types.py` — add PreprocessingState + PreprocessingStep Protocol

Add `PreprocessingState` (mutable dataclass holding per-run dicts OR concatenated X/Y matrices, plus metadata). Add `PreprocessingStep` Protocol with `name`, `apply(state, params) -> None`, `validate_params(params) -> list[str]`.

### 2. `plugins/_decorators.py` — add step decorator

Add `_preprocessing_steps` dict and `preprocessing_step = _make_decorator(...)`.

### 3. `registry.py` — add step support

Import `_preprocessing_steps`, add `self._preprocessing_steps`, getter, decorator, update `list_plugins()` and `_discover_entry_points()`.

### 4. Create `plugins/preprocessing_steps/` with built-in steps

Each step is a class with `@preprocessing_step("name")`:

| File | Step | Phase | Does |
|------|------|-------|------|
| `split.py` | `split` | per-run | Sets train_runs/test_runs from config |
| `trim.py` | `trim` | per-run | Trims start/end TRs from responses and features |
| `zscore.py` | `zscore` | both | Z-scores responses/features (per-run or concatenated) |
| `concatenate.py` | `concatenate` | pivot | hstacks features, vstacks runs, splits train/test |
| `delay.py` | `delay` | concatenated | Applies temporal delays to X matrices |
| `mean_center.py` | `mean_center` | both | Mean-centers without dividing by std |

### 5. `plugins/preprocessors/pipeline.py` — PipelinePreprocessor

`@preprocessor("pipeline")` class that:
1. Builds `PreprocessingState` from `ResponseData` + `FeatureData`
2. Resolves each step from `_preprocessing_steps` dict
3. Calls `step.apply(state, params)` sequentially
4. Returns `state.to_prepared_data()`
5. `validate_config` checks step names exist and validates params, plus ordering (split before concatenate, delay after concatenate)

### 6. `plugins/__init__.py` — register new modules

Add imports for step modules and pipeline preprocessor.

### 7. `config/schema.py` — update validation

When `preprocessing.type == "pipeline"`, validate `steps` is a list of dicts each with a `name` key. Skip trim_start/trim_end validation for pipeline type.

## Files Modified

- `denizenspipeline/core/types.py` — added PreprocessingState, PreprocessingStep
- `denizenspipeline/plugins/_decorators.py` — added step registry
- `denizenspipeline/registry.py` — added step getter/decorator/listing
- `denizenspipeline/plugins/__init__.py` — registered step modules
- `denizenspipeline/config/schema.py` — pipeline validation

## Files Created

- `denizenspipeline/plugins/preprocessing_steps/__init__.py`
- `denizenspipeline/plugins/preprocessing_steps/split.py`
- `denizenspipeline/plugins/preprocessing_steps/trim.py`
- `denizenspipeline/plugins/preprocessing_steps/zscore.py`
- `denizenspipeline/plugins/preprocessing_steps/concatenate.py`
- `denizenspipeline/plugins/preprocessing_steps/delay.py`
- `denizenspipeline/plugins/preprocessing_steps/mean_center.py`
- `denizenspipeline/plugins/preprocessors/pipeline.py`

## Verification

1. All 6 steps and pipeline preprocessor appear in `PluginRegistry.list_plugins()`
2. Existing `type: default` config works unchanged
3. `type: pipeline` with equivalent steps produces identical output to `type: default` (verified with `np.allclose`)
4. Validation catches missing steps, unknown steps, and bad ordering
