# Web UI

fMRIflow includes a browser-based interface for managing experiments, building pipelines, converting DICOMs, and monitoring runs. Start it with:

```bash
fmriflow serve
```

Then open `http://127.0.0.1:8000` in your browser.

The sidebar organizes features into three groups: **Preprocessing**, **Analysis**, and **Reference**.

---

## Preprocessing

### DICOM to BIDS

Convert raw DICOM images to BIDS format. Six tabs cover the full workflow:

**Tools** — Shows installed conversion tools (heudiconv, dcm2niix) and their status.

**Heuristics** — Browse and search available heuristic files. Each card shows the heuristic name, scanner pattern, and description.

**Scan** — Point at a DICOM directory to see what series it contains before converting.

**Manifests** — Browse previously generated conversion manifests. Validate them against configs to check compatibility.

**Convert** — Single-subject conversion form:

- Select a heuristic from the dropdown
- Set the BIDS output directory and source DICOM directory
- Enter subject ID and session
- Optional: dataset name, minimal metadata, overwrite, BIDS validation
- Click **Run** and watch live progress with streaming logs

**Batch** — Convert multiple subjects in parallel:

- **Shared settings** at the top: heuristic, BIDS dir, source root, max workers
- **Jobs table** below: add rows for each subject/session/source directory
- **Load YAML** to import a pre-configured batch, or **Export YAML** to save one
- **Save Config** stores the batch for re-use (saved to `~/.denizens/convert_configs/`)
- **Saved Configs** panel lists previously saved batches with Load/Delete actions
- Click **Run Batch** to start — progress shows per-job status badges (queued, running, done, failed), elapsed time, and expandable per-job logs

### Preprocessing Manager

Manage fMRI preprocessing (fmriprep, custom scripts) and their outputs. Four tabs:

**Backends** — Lists installed preprocessing backends with version and status.

**Manifests** — Browse completed preprocessing outputs. Each manifest records the backend, parameters, output space, and per-run QC metrics. Validate against an analysis config to check compatibility before running the pipeline.

**Collect** — Build a manifest from existing preprocessing outputs (e.g., from a previous fmriprep run). Specify the output directory and file pattern; the tool scans and organizes the files.

**Run** — Launch a preprocessing job:

- Select backend, set BIDS directory, output directory, work directory, subject ID
- Click **Run** for live progress with event streaming
- Manifest auto-refreshes on completion

---

## Analysis

### Dashboard

The main control center for running experiments.

**Config browser** (left sidebar):

- Lists all experiment YAML configs found in the project
- Search by filename, experiment name, subject, or model type
- Group by category
- Click a config to open its detail view

**Config detail** (main panel):

- Summary: experiment name, subject, model type, preprocessing settings
- Expandable raw YAML viewer
- Action buttons: **Run**, **Validate**, **Edit in Composer**
- Validation errors shown inline

**Live progress** (appears during a run):

- Real-time stage tracker with status badges (pending, running, done, failed)
- Event log with timestamps
- Elapsed timer
- Artifacts section after completion (view/download links)

**Run history** (bottom):

- Table of all past runs for the selected config
- Columns: date, experiment, subject, model, mean score, status
- Click to expand: summary metrics, stage timeline, artifacts, log tail

### Plugin Browser

Discover and inspect all available plugins, organized by processing stage (stimuli, responses, features, preprocessing, model, analysis, reporting).

- Search plugins by name or description
- Each card shows: name, category badge, dimension count, parameter count
- Expand a card to see its full parameter table (name, type, default, required, description)

### Pipeline Composer

Visually build analysis pipelines by selecting and configuring plugins.

**Config builder** (left panel) — sections for each pipeline stage:

- **Stimulus loader**: select type, language, modality
- **Response loader**: choose source (local, cloud, bids, preproc)
- **Features**: add/remove/reorder feature extraction steps, each with configurable parameters and autocomplete suggestions from saved configs
- **Preprocessing**: choose type (default or custom pipeline), add/remove/reorder steps
- **Split**: configure test runs
- **Model**: select model type and parameters
- **Analysis**: optional analysis plugins
- **Reporting**: toggle output formats

**Sidebar** (right panel):

- Experiment name and subject inputs
- Real-time config validation with error display
- Save, validate, and YAML import/export buttons

### Run Manager

Browse historical pipeline executions.

- **Run table**: date, experiment, subject, model, mean score, status badge
- **Expanded detail**: summary cards, stage timeline visualization, artifact list with view/download links, log tail (last 300 lines)
- Refresh to reload

### Plugin Editor

Write, validate, and register custom plugins directly in the browser.

**Sidebar**: list of user-created plugins, template categories (feature extractor, preprocessing step, reporter, analyzer, stimulus loader, response loader), new plugin button.

**Code editor**: full Python editing with syntax highlighting. Live validation runs as you type (~1 second debounce), checking syntax, method signatures, and protocol compliance.

**Status panel**: validation results, save/delete buttons, success/error messages.

**Workflow**: pick a template (or start blank) → write code → auto-validates → name and save → plugin is immediately available in the Composer and Plugin Browser.

Saved plugins go to `~/.denizens/plugins/` and are auto-loaded on server startup.

---

## Reference

### Error Knowledge Base

A searchable reference of known pipeline errors with symptoms, root causes, and fixes.

- **Search** across symptoms, root cause, fix text, and tags
- **Filter** by pipeline stage (stimuli, responses, features, preprocess, model, etc.)
- **Error cards** show: ID, stage badge, title, tags, symptom preview
- **Expanded view**: full symptoms, root cause, diagnosis steps, fix instructions, config notes, references

---

## Keyboard shortcuts and tips

- The sidebar auto-expands the group containing the active page
- Click the logo to return to the Dashboard from any view
- All long-running operations (conversions, preprocessing, pipeline runs) stream progress via WebSocket — you see results in real time
- Batch conversion configs saved through the UI are valid YAML files that work with `fmriflow convert batch --config`
