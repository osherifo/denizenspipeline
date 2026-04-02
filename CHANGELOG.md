# Changelog

All notable changes to fMRIflow are documented in this file.

---

## [Unreleased]

### 2026-03-05 — Pipeline Run Summary
**Author:** Omar Sherif
**Plan:** [docs/plans/pipeline-run-summary.md](docs/plans/pipeline-run-summary.md)

**Added:**
- `RunSummary` and `StageRecord` dataclasses in `core/run_summary.py` — captures per-stage timing, status, detail, and a config snapshot
- `save_timeline_chart()` in `core/run_chart.py` — matplotlib horizontal bar chart color-coded by stage status (green=ok, yellow=warning, red=failed, gray=skipped)
- `run_summary.json` and `run_timeline.png` saved to output directory after every run (success or failure)
- `Pipeline.last_context` — exposes the pipeline context even when the run fails, so the CLI can persist partial summaries

**Changed:**
- `orchestrator.py` — collects `StageRecord` list during the stage loop; attaches `RunSummary` to `ctx.run_summary` in a `finally` block
- `pipeline.py` — wraps `orchestrator.run()` in try/finally to preserve `last_context`
- `cli.py` — calls `_save_run_summary()` on both success and failure paths

**Unchanged:**
- No changes to any plugin, protocol, or config schema
- Existing output artifacts unaffected

**Files created:** `core/run_summary.py`, `core/run_chart.py`
**Files modified:** `orchestrator.py`, `pipeline.py`, `cli.py`

---

### 2026-03-04 — BIDS Response Loader
**Author:** Omar Sherif
**Plan:** [docs/plans/bids-response-loader.md](docs/plans/bids-response-loader.md)

**Added:**
- `BidsResponseLoader` (`@response_loader("bids")`) in `plugins/response_loaders/bids.py` — loads fMRI responses directly from BIDS-formatted datasets
- Auto-discovers sessions (`ses-*` dirs) or accepts explicit `sessions` list; supports sessionless layouts
- Parses BIDS filename entities to build run names (`ses-X_run-Y` or `run-Y`)
- Loads NIfTI data via nibabel with singleton-dim squeezing
- Reuses pycortex cortical masking from `LocalResponseLoader._apply_mask`
- Optional `run_map` remaps BIDS run labels to pipeline-friendly story names
- Optional dependency group: `bids = [nibabel>=5.0]`
- Example config: `experiments/experiment_bids.yaml`

**Config keys** (under `response:`):
- `path` — BIDS dataset root (required)
- `task` — BIDS task label (required)
- `sessions` — list of session labels (optional, auto-discovered)
- `suffix` — file suffix, default `bold`
- `extension` — file extension, default `.nii.gz`
- `run_map` — dict remapping run names
- `mask_type` — pycortex mask type, default `thick`

**Plugin inventory update:**

| Type             | Count | New   |
|------------------|-------|-------|
| Response Loaders | 3     | +bids |

---

### 2026-03-04 — Multi-Modal Stimulus Support
**Author:** Omar Sherif
**Plan:** [docs/plans/multi-modal-stimulus-support.md](docs/plans/multi-modal-stimulus-support.md)

**Added:**
- `LanguageStim`, `AudioStim`, `VisualStim` frozen dataclasses in `core/types.py` — typed stimulus containers
- `StimRun.stimulus` field replacing bare `textgrid`/`trfile`; backward-compatible `@property` accessors keep all 11 existing extractors working unchanged
- `core/alignment.py` — `align_to_trs()` utility for binning high-rate features into TR windows via `np.searchsorted`
- 2 new stimulus loaders: `audio` (librosa, loads .wav files) and `video` (cv2, stores metadata only — frames decoded on demand)
- 4 new feature extractors: `mel_spectrogram`, `rms_energy` (audio), `luminance`, `motion_energy` (visual)
- Optional dependency groups: `audio = [librosa, soundfile]`, `video = [opencv-python]`
- Schema validation: `"visual"` modality, `stimulus.path` required for audio/video loaders

**Changed:**
- `textgrid.py` loader wraps textgrid/trfile in `LanguageStim` before constructing `StimRun`
- Test fixtures updated to use `stimulus=LanguageStim(...)` constructor

**Unchanged:**
- All existing language feature extractors work via backward-compat properties — zero code changes
- `type: default` and `type: pipeline` preprocessors unaffected
- No orchestrator changes

**Plugin inventory update:**

| Type               | Count | New |
|--------------------|-------|-----|
| Stimulus Loaders   | 4     | +audio, +video |
| Feature Extractors | 15    | +mel_spectrogram, +rms_energy, +luminance, +motion_energy |

---

### 2026-03-04 — Postprocessing Analyze Stage
**Author:** Omar Sherif
**Proposal:** [docs/proposals/postprocessing-analyze-stage.md](docs/proposals/postprocessing-analyze-stage.md)

**Added:**
- New `analyze` pipeline stage between `model` and `report` (stage 6 of 7)
- `Analyzer` Protocol in `core/types.py` — `name`, `analyze(context, config)`, `validate_config(config)`
- `VariancePartition` and `WeightAnalysis` frozen dataclasses in `core/types.py`
- `analyzer` decorator in `plugins/_decorators.py` and full registry support
- 2 built-in analyzers in `plugins/analyzers/`:
  - `variance_partition` — unique variance per feature via leave-one-out weight ablation
  - `weight_analysis` — decomposes delayed weights into per-feature importance and temporal profiles
- Analyzer resolution, validation, and execution in `orchestrator.py`
- Schema validation for optional `analysis` config section
- `fmriflow list analyze` shows available analyzers
- 3 example configs: `analysis_weights.yaml`, `analysis_variance.yaml`, `analysis_full.yaml`

**Design:**
- Analyzers read from context and write results back under `analysis.*` keys
- Each analyzer defines its own output type — no forced single container
- Stage is optional: no `analysis:` in config means the stage is skipped
- Reporter protocol unchanged — reporters can optionally check for analysis keys via `context.has()`

**Unchanged:**
- All existing configs work without modification — analyze stage is a no-op when unconfigured
- Reporter protocol and existing reporters untouched

---

### 2026-03-04 — `fmriflow list` CLI command
**Author:** Omar Sherif

**Added:**
- `fmriflow list` — lists all pipeline stages with descriptions
- `fmriflow list plugins` — lists all registered plugins across every category
- `fmriflow list <stage>` — lists plugins available for a specific stage (e.g. `fmriflow list preprocess`, `fmriflow list features`)
- `stages_table()` UI helper in `ui.py`
- `plugins_table()` now accepts a custom title and includes response_readers and preprocessing_steps categories

**Files modified:** `cli.py`, `ui.py`

---

### 2026-03-04 — Stackable Preprocessing Pipeline
**Author:** Omar Sherif
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
**Author:** Omar Sherif

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
| Response Readers   | 6     | npz_per_run, hdf5_per_run, single_pickle, single_hdf5, auto, phact_hdf |
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
- CLI entry point (`fmriflow run/validate/plugins`)
- Bootstrap ridge regression preserved from v1
- Config checkpointing and resume support
