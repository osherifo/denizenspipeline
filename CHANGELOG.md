# Changelog

All notable changes to fMRIflow are documented in this file.
Format follows [Conventional Changelog](https://www.conventionalcommits.org/).

---

## [Unreleased]

---

## v2.0.0-alpha.3 (2026-04-16)

### Features
- **fe:** visual pipeline graph builder built on React Flow
- **fe:** YAML panel on the pipeline graph with bidirectional sync
- **fe:** inline YAML editor in dashboard, replacing 'Edit in Composer'
- **fe:** duplicate button on dashboard config detail
- **fe:** side-by-side run comparison view; drag-reorder image rows; auto-align artifacts with user-overridable pairing; extend from 2 to N runs (no cap)
- **fe:** per-type result viewer registry with drag-and-drop reordering and per-viewer delete
- **convert:** heuristic code editor and template creator
- **server/fe:** fmriprep structured options + autoflatten integration + preprocessing UI
- **server:** stream autoflatten logs via WebSocket
- **fe:** flatmap previews shown after autoflatten runs
- **convert:** saved config store for conversion presets — YAML-backed CRUD in `~/.fmriflow/convert_configs/`
- **convert:** batch processing for heudiconv conversions — parallel multi-subject runs with WebSocket progress
- **convert:** initial DICOM-to-BIDS conversion module — heudiconv wrapper, heuristic registry, scan/dry-run/doctor CLI
- **fe:** sidebar navigation with category grouping — moved from top tabs to side nav with Preprocessing/Analysis/Reference categories
- **fe:** save/load/delete UI for conversion configs in BatchForm

### Bug Fixes
- **server:** align model validator's required method from `fit_predict` to `fit`
- **convert:** path traversal validation + `is_relative_to()` for heuristic names
- **server:** container existence check for docker images and `docker://` URIs
- **cli:** drop redundant `--parallel` flag from autoflatten
- **server:** missed `preprocessing_type` reference in configs route

### Other Changes
- **all:** rename internal `plugin` concept to `module` (user modules now live in `~/.fmriflow/modules/`)
- **all:** rename analysis stage `preprocessing` → `preparation`, drop back-compat shims
- **cli:** browser auto-open is now opt-in via `--open`
- **docs:** add autoflatten and pipeline graph docs to mkdocs site
- **infra:** re-add MIT license after history rewrite; rebuild frontend assets
- **test:** name-based registry assertions; `StimRun` construction; `MockTRFile.avgtr` and stale `response_readers` test API

---

## v2.0.0-alpha.2 (2026-04-02)

### Bug Fixes
- **fe:** add missing plugins route to hash router — Plugins tab was falling through to dashboard

### Other Changes
- **chore:** add MIT license file

### Bug Fixes
- **server:** close FileHandler on run completion to prevent leak
- **fe:** replace React namespace types with direct imports across all TSX files

### Other Changes
- **chore:** rename project from `denizenspipeline` to `fmriflow` — package, CLI, env vars, user config dir, all imports
- **chore:** update `.gitignore` to exclude `heuristics/` and `CHANGES`

---

## v2.0.0-alpha.1 (2026-03-05)

### Features
- **cli:** add `fmriflow list` command — lists stages, plugins, and plugins per stage
- **cli:** add `fmriflow preproc` subcommand — run, collect, validate, info, doctor for fMRI preprocessing
- **cli:** add `fmriflow convert` subcommand — run, scan, dry-run, collect, validate, batch, heuristics, doctor
- **plugins:** add pipeline run summary — `RunSummary`/`StageRecord` dataclasses, timeline chart, JSON output
- **plugins:** add BIDS response loader — loads fMRI data directly from BIDS datasets via nibabel
- **plugins:** add multi-modal stimulus support — `LanguageStim`, `AudioStim`, `VisualStim` types; audio/video loaders
- **plugins:** add 4 new feature extractors — `mel_spectrogram`, `rms_energy` (audio), `luminance`, `motion_energy` (visual)
- **plugins:** add postprocessing analyze stage — `variance_partition` and `weight_analysis` analyzers
- **plugins:** add stackable preprocessing pipeline — 6 composable steps (`split`, `trim`, `zscore`, `concatenate`, `delay`, `mean_center`)
- **plugins:** standardize all 36 plugins to decorator-based registration
- **plugins:** add GPT-2 and BERT-large feature extractors
- **server:** add frontend web UI — plugin browser, pipeline composer/editor, run manager with WebSocket progress
- **server:** add autocomplete for config fields from saved experiments
- **fe:** add progress viewer for pipeline runs
- **fe:** add pipeline editor with Monaco

### Bug Fixes
- **plugins:** raise `ValueError` on per-run TR mismatch in `DefaultPreprocessor` instead of silent warning
- **plugins:** fix custom trimming for features and response data

### Other Changes
- **docs:** add `trim_responses` to config reference and fix `trim_features` description
- **infra:** remove `node_modules` from tracking, clean `__pycache__` directories

---

## v0.2.0-alpha.1 — Initial v2 Architecture

- Plugin-based pipeline with 6 sequential stages
- YAML-driven configuration with inheritance and env var substitution
- CLI entry point (`fmriflow run/validate/plugins`)
- Bootstrap ridge regression preserved from v1
- Config checkpointing and resume support
