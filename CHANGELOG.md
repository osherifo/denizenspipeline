# Changelog

All notable changes to fMRIflow are documented in this file.
Format follows [Conventional Changelog](https://www.conventionalcommits.org/).

---

## [Unreleased]

### Features
- **convert:** add saved config store for conversion presets — YAML-backed CRUD in `~/.fmriflow/convert_configs/`
- **convert:** add batch processing for heudiconv conversions — parallel multi-subject runs with WebSocket progress
- **convert:** initial DICOM-to-BIDS conversion module — heudiconv wrapper, heuristic registry, scan/dry-run/doctor CLI
- **fe:** add sidebar navigation with category grouping — moved from top tabs to side nav with Preprocessing/Analysis/Reference categories
- **fe:** add save/load/delete UI for conversion configs in BatchForm

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
