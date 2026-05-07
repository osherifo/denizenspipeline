# Changelog

All notable changes to fMRIflow are documented in this file.
Format follows [Conventional Changelog](https://www.conventionalcommits.org/).

---

## [Unreleased]

---

## v2.0.0-alpha.4 (2026-05-07)

### Features

**Containerization**
- **infra:** slim + full Docker images with one-step `docker compose up` (#60). Slim delegates fmriprep to host (docker-out-of-docker or apptainer); full bakes fmriprep + FreeSurfer + ANTs (`FROM nipreps/fmriprep:24.1.1`)
- **infra:** Docker user guide wired into mkdocs nav

**Live nipype DAG monitoring**
- **preproc:** double-click a Preproc card → live DAG modal with per-node states
- **preproc:** live nipype-node monitoring under the Workflows graph
- **workflows:** hierarchical, collapsible, searchable node list on the left of the DAG modal
- **workflows:** per-node fmriprep output drawer in the DAG modal
- **workflows:** merge cached leaves from `work_dir`, FIFO leaf matching, run-end sweep + backfill script
- **qc:** select node → pan/zoom DAG canvas to centre it
- **workflows:** straight edges + adaptive layout for workflow cards

**Structural QC reviewer**
- **qc:** structural-preproc reviewer sign-off (browser + freeview)
- **qc:** cross-dataset QC Reviews view + status pill on manifest list
- **qc:** taller niivue canvas + view + surface pickers (pial / white / inflated)
- **qc:** fullscreen toggle + multi-surface overlay
- **qc:** structural 3D viewer opens fullscreen directly
- **qc:** Volume on/off toggle to hide T1 'skull' in 3D
- **qc:** per-surface alpha sliders + meshXRay so transparency renders
- **workflows:** Structural QC drill-in + cross-dir manifest discovery

**Post-preproc workflows**
- **post-preproc:** post-fmriprep nipype-style stage with ReactFlow builder
- **post-preproc:** nipype-style workflows, subworkflows, MapNode
- **post-preproc:** in-place code editor + workflow-stage node color
- **post-preproc:** per-handle literal input paths in side panel
- **workflows:** post_preproc as a stage in the overarching workflow

**Workflow orchestrator (Phase 2)**
- **server:** end-to-end workflow orchestrator chaining convert → preproc → autoflatten → post-preproc → analysis
- **fe:** Workflows view + top-level Pipeline nav entry
- **fe:** ReactFlow graph for workflow runs, auto-opens, exposes per-stage logs
- **fe:** workflow graph decomposes analysis into its inner stages
- **fe:** live log pane under the workflow graph
- **server:** emit per-stage events file from the analysis subprocess
- **workflows:** edit + duplicate workflow configs
- **workflow:** reattach orchestrator on server restart

**Detach / reattach long-running jobs (#54, #55)**
- **server:** detach heudiconv + reattach convert runs on restart
- **server:** detach autoflatten CLI + reattach on restart
- **server:** detach analysis pipelines + reattach on restart
- **fe:** Recent Runs / In-Flight panels for convert, autoflatten, analysis
- **fe:** Configs tabs for convert + autoflatten + preproc, log viewer for in-flight runs

**YAML configs (Phase 1, #56)**
- **server:** consistent YAML configs across convert + autoflatten + preproc
- **server:** YAML-driven autoflatten configs via `/autoflatten/configs`
- **server:** YAML-driven preprocessing configs via `/preproc/configs` API
- **server:** run convert YAML configs via `/convert/configs/{file}/run`
- **fe:** preprocessing configs browser tab

**Other**
- **fe:** show full configs in run comparison
- **fe:** replace browser dialogs with fmriflow-branded modal
- **autoflatten:** edit + duplicate configs, unify tab bar with other managers
- **autoflatten:** show run results (flatmaps + pycortex + patches) in log modal
- **modules:** view + edit module source from the Module Browser
- **triage:** automatic error capture v1
- **fe:** delete previous runs from every In-Flight panel + Workflows
- **preproc:** run fmriprep via apptainer with skip-bids-validation toggle

### Bug Fixes

**Docker / packaging**
- **packaging:** force-include `server/static` in wheel (#64) — frontend now actually serves on `GET /` in containerized images
- **docker:** copy frontend bundle before pip install (#64)
- **docker:** add build-essential + opencv runtime libs to slim (#63) — pycortex + cv2 build cleanly
- **docker:** install ml/himalaya/audio/video/cloud/viz extras so the server boots (#62)
- **docker:** include autoflatten extra in slim and full
- **docker:** use PUID/PGID vars consistently in compose and docs

**QC**
- **qc:** hydrate nipype_jsonl_path on registry-fallback get_run
- **qc:** include extension in niivue volume name to avoid getFileExt crash
- **qc:** validate fs-file suffix on requested rel, not resolved target
- **qc:** serve fmriprep report's relative figure assets
- **qc:** drawer Close → arrow that only hides the outputs panel
- **qc:** replace per-surface alpha with global X-ray slider that actually works

**Server**
- **server:** capture full traceback on stage failures
- **server:** persist full resolved config in `run_summary.config_snapshot`
- **server:** restore env=child_env on analysis subprocess
- **server:** surface terminal fmriprep errors immediately via log tailer
- **server:** tail analysis events.jsonl into the WebSocket stream
- **server:** write each analysis run to its own output subdirectory
- **server:** rename Thread subclass `_stop` attr to `_stop_flag`

**Frontend**
- **fe:** workflow log modal handles convert batches (404 on batch_id)
- **fe:** render log event messages in dashboard event log
- **fe:** show KB matches + Save-to-KB in per-stage log modals
- **fe:** use 'prepare' stage name in run dashboard

**Other**
- **convert:** accept multiple DICOM roots per heudiconv invocation
- **autoflatten:** include subjects_dir in get_run registry-fallback path
- **autoflatten:** replace removed `cortex.db.get_list()` call
- **workflows:** nipype strip stays compact; add View DAG button
- **test:** update DicomScanResult mock + assertion to current shape (#61)
- general: close `log_fh` + WebSocket in terminal branches; batch-detection, API types, and `select()` error handling; error handling in `AutoflattenConfigBrowser.reload()`

### Tests

- **frontend:** Vitest + MSW + Playwright harness — 219 unit tests + 10 e2e flows (#58)
- **frontend:** cover live-nipype + post-preproc + structural-qc features
- **frontend:** bind vite dev to 127.0.0.1 for Playwright webServer in CI
- **frontend:** lower coverage thresholds to current floor

### Docs

- **docs:** Workflows guide
- **docs:** Docker quickstart (slim + full + apptainer-on-host)
- **docs:** post_preproc as a workflow stage
- **docs:** detach-reattach for convert / autoflatten / analysis runs
- **docs:** YAML config flow for convert + autoflatten
- **docs:** QC Reviews view + manifest status pill in the structural-qc guide
- **docs:** niivue toolbar (view / volume / surfaces / X-ray / fullscreen) + Workflows drill-in

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
