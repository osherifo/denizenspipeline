# Changelog

All notable changes to DenizensPipeline are documented in this file.

---

## [Unreleased]

### 2026-03-04 — Stackable Preprocessing Pipeline
**Author:** Omar Shmait
**Plan:** [docs/plans/stackable-preprocessing-pipeline.md](docs/plans/stackable-preprocessing-pipeline.md)

**Added:**
- `PreprocessingState` mutable dataclass in `core/types.py` — holds per-run dicts or concatenated matrices, mutated in place by steps
- `PreprocessingStep` Protocol in `core/types.py` — `name`, `apply(state, params)`, `validate_params(params)`
- `preprocessing_step` decorator in `plugins/_decorators.py` and full registry support (getter, entry points, listing)
- 6 built-in preprocessing steps in `plugins/preprocessing_steps/`: `split`, `trim`, `zscore`, `concatenate`, `delay`, `mean_center`
- `PipelinePreprocessor` (`@preprocessor("pipeline")`) in `plugins/preprocessors/pipeline.py` — chains steps from YAML config
- Pipeline-aware validation in `config/schema.py` (validates `steps` list, skips trim params for pipeline type)
- 3 example pipeline configs in `experiments/`: `pipeline_default.yaml`, `pipeline_no_delay.yaml`, `pipeline_mean_center.yaml`

**Changed:**
- Pipeline steps are fully flexible — any order, any subset. No enforced ordering constraints. The user controls the exact sequence via the YAML `steps` list.

**Unchanged:**
- `type: default` preprocessor works exactly as before — fully backward-compatible
- No orchestrator changes — `PipelinePreprocessor` satisfies the existing `Preprocessor` protocol

**Plugin inventory update:**

| Type                | Count | New |
|---------------------|-------|-----|
| Preprocessors       | 3     | +pipeline |
| Preprocessing Steps | 6     | +split, trim, zscore, concatenate, delay, mean_center |

---

### 2026-03-04 11:28 CET — Plugin Registry Decorator Standardization
**Author:** Omar Shmait

**Added:**
- Central decorator module `plugins/_decorators.py` with decorator factories for all 8 plugin types (`@stimulus_loader`, `@response_loader`, `@response_reader`, `@feature_extractor`, `@feature_source`, `@preprocessor`, `@model`, `@reporter`)
- `ResponseReader` Protocol in `core/types.py` for response reader plugins
- Response reader support in `PluginRegistry` (decorator, getter, entry_points discovery, listing)
- `GPT2Extractor` registration (was implemented but never registered)

**Changed:**
- All 36 plugin classes now self-register via decorators — single consistent pattern across the entire codebase
- `PluginRegistry` uses `_decorators` module-level dicts directly as its backing store (single source of truth, no copying)
- `register_builtins()` simplified to just importing plugin modules (decorator fires on import)
- Response readers converted from bare functions to proper classes with `name`, `read()`, and `validate_config()` methods

**Plugin inventory (36 total):**

| Type               | Count | Plugins |
|--------------------|-------|---------|
| Stimulus Loaders   | 2     | textgrid, skip |
| Response Loaders   | 2     | cloud, local |
| Response Readers   | 6     | npz_per_run, hdf5_per_run, single_pickle, single_hdf5, auto, multiphase_hdf |
| Feature Extractors | 11    | numwords, numletters, numphonemes, word_length_std, english1000, letters, phonemes, word2vec, bert, fasttext, gpt2 |
| Feature Sources    | 4     | compute, filesystem, cloud, grouped_hdf |
| Preprocessors      | 2     | default, pre_prepared |
| Models             | 4     | bootstrap_ridge, himalaya_ridge, banded_ridge, multiple_kernel_ridge |
| Reporters          | 5     | metrics, flatmap, weights, histogram, webgl |

**Files modified (26):**
`plugins/_decorators.py` (new), `core/types.py`, `registry.py`, `plugins/__init__.py`, and all 22 plugin files across `stimulus_loaders/`, `response_loaders/`, `feature_extractors/`, `feature_sources/`, `preprocessors/`, `models/`, `reporters/`.

---

## [0.2.0-alpha1] — Initial v2 Architecture

- Plugin-based pipeline with 6 sequential stages
- YAML-driven configuration with inheritance and env var substitution
- CLI entry point (`denizens run/validate/plugins`)
- Bootstrap ridge regression preserved from v1
- Config checkpointing and resume support
