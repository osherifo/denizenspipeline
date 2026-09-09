# Web UI

fMRIflow includes a browser-based interface for managing experiments, building pipelines, converting DICOMs, and monitoring runs. Start it with:

```bash
fmriflow serve
```

Then open `http://127.0.0.1:8000` in your browser.

The sidebar organizes features into four groups: **Pipeline**, **Preprocessing**, **Analysis**, and **Reference**. The installed fMRIflow version is shown under the logo at the top of the sidebar.

---

## Pipeline

### Workflows

End-to-end orchestration across all four stages (convert, preproc, autoflatten, analysis). Each workflow is a single YAML under `$FMRIFLOW_HOME/configs/workflows/` that references existing per-stage configs. Clicking Run kicks off the stages in order, stopping on the first failure; each stage's child run inherits its own detach/reattach semantics. See the dedicated [Workflows guide](workflows.md) for the schema, orchestration semantics, and API.

---

## Preprocessing

### DICOM to BIDS

Convert raw DICOM images to BIDS format. Seven tabs cover the full workflow:

**Tools** — Shows installed conversion tools (heudiconv, dcm2niix) and their status.

**Heuristics** — Browse and search available heuristic files. Each card shows the heuristic name, scanner pattern, and description.

**Scan** — Point at a DICOM directory to see what series it contains before converting.

**Manifests** — Browse previously generated conversion manifests. Validate them against configs to check compatibility.

**Configs** — Browse YAML conversion configs saved under `./experiments/convert/` (pre-migration configs at `~/.fmriflow/convert_configs/` are also listed read-only with a LEGACY tag). Clicking one shows a summary grid + the raw YAML, with a **Run** button that dispatches either a single or batch conversion based on the file's shape. See [DICOM → BIDS → Saved configs](dicom-to-bids.md#saved-configs) for the schema.

**Convert** — Single-subject conversion form (path fields have a **Browse…** button that lists directories as the server sees them):

- Select a heuristic from the dropdown
- Set the BIDS output directory and source DICOM directory
- Enter subject ID and session
- Optional: dataset name, minimal metadata, overwrite, BIDS validation
- Click **Run** and watch live progress with streaming logs

**Batch** — Convert multiple subjects in parallel:

- **Shared settings** at the top: heuristic, BIDS dir, source root, max workers
- **Jobs table** below: add rows for each subject/session/source directory
- **Load YAML** to import a pre-configured batch, or **Export YAML** to save one
- **Save Config** stores the batch for re-use (saved to `~/.fmriflow/convert_configs/`)
- **Saved Configs** panel lists previously saved batches with Load/Delete actions
- Click **Run Batch** to start — progress shows per-job status badges (queued, running, done, failed), elapsed time, and expandable per-job logs

### Preprocessing

One page, four tabs, over one pipeline graph. See the [Preprocessing guide](preprocessing.md).

**Build** — Templates (`fmriprep_full`, `fmriprep_anat_only`, `fmriprep_func_precomputed_anat`, `derivatives_smooth_regress`, `reference_nipype`) and saved pipelines on the left; the editor in the middle as a **Simple** chain of cards or a **Graph** (drag ports to connect); the selected node's grouped parameters, input bindings, ×N iteration and manifest role on the right, above the **Run** panel (subject, paths, plugin, cache, rerun-from, abort-on-bad-checkpoint).

**Runs** — Every pipeline run. The detail shows the graph with live node status, the checkpoint filmstrip (verdict-coloured frames with thumbnails and the metric / bound table), a node's outputs drawer (NIfTI viewer, reports, JSON, pickles, crash files), the fmriprep node's **Inner DAG**, the log, the event stream, and a **Resume / Restart** choice for lost or failed runs.

**Library** — Browse nodes by kind (source / node / app / workflow) and source (built-in / user), with preflight status, parameter schema and source code. **New node** opens a Monaco scaffold saved to `$FMRIFLOW_HOME/addons/nodes/`; **Import nipype pipeline** turns an existing `.py` into a composite node.

**Outputs** — Manifests on disk (validate against an analysis config; structural-QC status per subject) and **Collect** existing derivatives into a manifest.

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

**In-Flight Analysis Runs panel** (top of the right pane):

- Lists active + recent detached analysis runs, auto-refreshing every 5 s while anything is running.
- `Log` opens a modal with run metadata + last 200 lines of `stdout.log`.
- `Cancel` sends `SIGTERM` to the process group with a `SIGKILL` chaser after 5 s.
- Runs reattached from disk (after a server restart) show a yellow `REATTACHED` tag — see the ["Long-running analysis runs" section below](#long-running-analysis-runs--detach--reattach) for details.

**Run history** (bottom):

- Table of all past runs for the selected config
- Columns: date, experiment, subject, model, mean score, status
- Click to expand: summary metrics, stage timeline, artifacts, log tail

### Module Browser

Discover and inspect all available modules, organized by processing stage.

- **Scope tabs** at the top — Subject (7 stages: stimuli → report),
  Group (group_analyze, group_report), Study (study_analyze,
  study_report), **QA** (qa_reporters grouped by the subject pipeline
  stage they target). Each tab shows a count badge with the total
  modules registered in that scope.
- Search modules by name or description (filters within the active scope)
- Each card shows: name, category badge, dimension count, parameter count
- Expand a card to see its full parameter table (name, type, default, required, description)
- The QA tab borrows the subject pipeline stage layout — a
  `qa_reporter` decorated with `stage="prepare"` shows up in the
  **prepare** column under that tab — without leaking into the
  regular Subject columns, which stay focused on pipeline plugins.

**+ New module** (next to the search bar) opens a dialog that
creates a new plugin from a starter template:

- **Category** — filtered to what the active tab can host:
  Subject creates `feature_extractors`, `reporters`, `analyzers`,
  `stimulus_loaders`, etc.; Group creates `group_analyzers` /
  `group_reporters`; Study creates `study_analyzers` /
  `study_reporters`; **QA** creates `qa_reporters`.
- **Stage** (shown only when category is `qa_reporters`) — picks
  which subject pipeline stage the reporter attaches to (`stimuli`,
  `responses`, `features`, `prepare`, or `model`). The template's
  `value` argument type matches the stage (`ModelResult` for `model`,
  `PreparedData` for `prepare`, etc.).
- **Name** — snake_case; the dialog validates the format inline.

Submit opens the same Monaco editor used for **Edit source**, but
pre-loaded with the rendered template and a Save button that's
enabled from the start. Save & Reload writes the file to
`$FMRIFLOW_HOME/addons/modules/` and registers the class in the live
registry in one shot — the new module appears in the browser the
moment you click **Back**.

### Composer

Build encoding-model pipelines. A **scope tab bar** at the top
switches between **Subject**, **Group**, and **Study** composers —
each tab has its own form, its own YAML editor, and its own
state, so switching between them never loses unsaved edits in
another scope.

#### Subject scope

A vertical strip of seven collapsible **stage cards** (stimuli,
responses, features, prepare, model, analyze, report). Each card
holds the modules plugged into that stage plus their parameters.

**Stage cards** (left column):

- The card header shows the stage number, name, fill status (badge
  colour), and a one-line summary. Click to expand/collapse.
- **Stimuli, Responses, Model**: pick a single module from a
  dropdown, then fill its `ParamForm`. Response loaders that need
  a separate reader (e.g. `local`) reveal a second slot inline.
- **Features, Analyze**: a stack of mini-cards. Add, remove,
  reorder (↑ / ↓ buttons), and edit each entry independently.
- **Preparation**: a checkbox toggles between the default single
  preparer and a pipeline of preparation steps (same stack UX as
  Features).
- **Reporting**: checkbox group for output formats + an output
  directory input.

**Pipeline preview** (below the strip): a read-only ReactFlow
graph of the seven stages, coloured by fill status (cyan = filled,
grey = empty, red = validation error). Clicking a node scrolls
the matching card into view.

**Right column**: a Monaco YAML editor that mirrors the form. The
form is the source of truth; raw edits in YAML are applied after
800 ms of pause. Validate, Copy YAML, and Reset live in the top
action bar.

The composer reads and writes
`$FMRIFLOW_HOME/configs/analysis/*.yaml`. See the
[Working Directory](working-dir.md) guide for the surrounding
layout.

#### Group scope

Author a cross-subject group config. Form sections:

- **Top fields**: `group` name, `subjects` (comma-separated list),
  `output_dir`.
- **Subject template**: the same seven stage cards the Subject
  composer renders, scoped to `subject_template.*`. Edits here flow
  into the YAML editor's `subject_template:` block; every subject
  in the group inherits this pipeline unless overridden.
- **Subject overrides**: a list of per-subject sparse override
  dicts. Pick a subject from the dropdown (only subjects defined
  above are offered), click **+ Add override**, and edit the
  partial dict in its own mini Monaco editor (~160 px tall).
  Overrides are deep-merged on top of the template at run time —
  set just the key you want to deviate (e.g.
  `model: {params: {alpha: 0.5}}`).
- **Group analyze** / **Group report**: stacks of
  `group_analyzer` / `group_reporter` plugin picks, same UX as the
  Subject composer's analyze stage.

The right pane's Monaco YAML editor stays the source of truth for
anything the form doesn't surface; form edits sync into it on a
500 ms debounce, and raw YAML edits apply back after 800 ms.

#### Study scope

Author a cross-group study config:

- **Top fields**: `study` name, `output_dir`.
- **Groups**: a list of `(name, config)` pairs pointing at saved
  group YAMLs. The config-path picker has a datalist sourced from
  the dashboard's saved-config index so you pick by filename.
- **Study analyze** / **Study report**: stacks of
  `study_analyzer` / `study_reporter` plugin picks.
- Right pane: Monaco YAML editor.

`/api/config/validate` sniffs the YAML shape (`subject` vs
`group:` + `subjects:` vs `study:` + `groups:`) and dispatches to
the right schema validator, so the Validate button works from any
scope tab without an extra round-trip.

### Run Manager

Browse historical pipeline executions. There are three sibling views
in the sidebar — **Subject Runs**, **Group Runs**, **Study Runs** —
each scoped to one orchestrator level. They share the same detail
panel features:

- **Run table**: date, experiment / group / study, status badge,
  primary metric where applicable.
- **Expanded detail**: summary cards, stage timeline visualization,
  artifact list with view/download links, log tail (last 300 lines).
- **View graph** opens the pipeline graph for that run in a modal.
  In a *finished* group or study run, clicking a child node (a group
  inside a study, a subject inside a group) opens it as a **second
  pane to the right** instead of replacing the current view —
  click subject inside that pane and a third pane opens. Each pane
  has its own ✕ that closes only itself and anything drilled from it.
  Same drilldown chain works for in-flight runs.
- **View YAML** opens the run's resolved `config_snapshot` as YAML
  in a read-only Monaco editor with Copy + Download. This is the
  *resolved* config (defaults + env vars + inheritance expanded), not
  the original on-disk file.
- Refresh to reload.

#### Live progress dashboard

The Dashboard switches between three Live-Progress panels by run
kind. The selected progress panel shows a streaming event log:
each subject's `▶ stage` / `✓ stage` / `✗ stage` lines are prefixed
with `group/subject:` so you can tell which subject is in which
stage even when several run concurrently.

The graph viewer in the dashboard lights up *running* subject /
group nodes the moment their first lifecycle event fires (cyan),
flipping to green / red when each finishes — without waiting for
any stage records to land. Saved runs colour purely from their
final stage statuses.

#### QA tab on graph nodes

Every stage node in the graph viewer has a **QA tab** that surfaces
any `@qa_reporter` artifacts the run wrote for that stage
(`<run_dir>/<subject>/qa/<stage>/`). Each artifact is shown inline
(PNG) or as a download link (JSON, etc.). A **Regenerate** button
re-runs only the QA plugins for that stage by reloading the saved
intermediate (when `intermediates:` was on) — no need to rerun the
model just to tweak a plot.

### Module Editor

Write, validate, and register custom modules directly in the browser.

**Sidebar**: list of user-created modules, template categories (feature extractor, preparation step, reporter, analyzer, stimulus loader, response loader), new module button.

**Code editor**: full Python editing with syntax highlighting. Live validation runs as you type (~1 second debounce), checking syntax, method signatures, and protocol compliance.

**Status panel**: validation results, save/delete buttons, success/error messages.

**Workflow**: pick a template (or start blank) → write code → auto-validates → name and save → module is immediately available in the Composer and Module Browser.

Saved modules go to `$FMRIFLOW_HOME/addons/modules/` and are auto-loaded on server startup.

---

## Reference

### Error Knowledge Base

A searchable reference of known pipeline errors with symptoms, root causes, and fixes. The server loads entries from your local error knowledge base — `$FMRIFLOW_ERRORS/` (default `$FMRIFLOW_HOME/errors/`). This is a per-user directory of `*.yaml` entries; it is never committed and the location is configurable via the `$FMRIFLOW_ERRORS` environment variable or the Settings tab.

If you have not added any error definitions there yet, this page may be empty by default.

- **Search** across symptoms, root cause, fix text, and tags
- **Filter** by pipeline stage (stimuli, responses, features, preprocess, model, etc.)
- **Error cards** show: ID, stage badge, title, tags, symptom preview
- **Expanded view**: for available entries, full symptoms, root cause, diagnosis steps, fix instructions, config notes, references

### Documentation

Opens this documentation site in a new browser tab. The server ships a built copy of the docs and serves it at `/documentation/`, so it works offline and inside the Docker container — no separate docs hosting needed.

### Settings

Browser UI for the working-directory env vars: `FMRIFLOW_HOME`, `FMRIFLOW_DATA`, `FS_LICENSE`, `FMRIFLOW_SINGULARITY_BIN`. See [Working Directory](working-dir.md#editing-paths-from-the-settings-tab) for the layout this controls.

- Each row shows a **source badge** (`env` / `persisted` / `default`) so you can tell which tier the running server is using.
- Rows shadowed by a shell-exported env var are **locked** — unset the var in your shell to edit the persisted value.
- **Save** writes `~/.config/fmriflow/settings.json` and shows a "restart fmriflow" banner — services cache the resolved layout at startup, so live re-apply is not safe.
- **Create directories if they don't exist** checkbox (default on) — `mkdir -p`s `FMRIFLOW_HOME` / `FMRIFLOW_DATA` if they don't exist yet, so you don't have to drop into a terminal.
- The **Resolved layout** table at the bottom mirrors `fmriflow paths` plus FreeSurfer-license and `subjects.json` presence.

### Result locations (multiple result roots)

By default the dashboard scans one location for results and runs — your primary
`$FMRIFLOW_HOME`. The **Result locations** section of the Settings tab lets you
register additional, **read-only** roots so the scanners also surface results
and runs stored elsewhere (another disk, an archive, a shared lab tree).

- Each extra root should be a `$FMRIFLOW_HOME`-shaped tree — i.e. it has
  `data/results/`, `study_runs/`, `group_runs/`, and/or `runs/` beneath it.
  Adding **one path** makes all of those visible.
- Extra roots are **read-only**: new runs are always written to the primary
  root, and runs discovered in an extra root cannot be deleted from the UI.
- Changes apply on the **next refresh** — no restart needed (unlike the path
  settings above). Each root shows a `primary` / `read-only` / `unreachable`
  badge; an offline mount is skipped gracefully rather than breaking the scan.
- Runs from a non-primary root carry a small `↪ <root>` badge in the run lists
  so you can see where each one lives.
- Headless/CI: set `$FMRIFLOW_RESULT_ROOTS` to an `os.pathsep`-separated list of
  paths; it overrides the persisted list. API: `GET/POST/DELETE
  /api/settings/result-roots`.

> Identity note: runs are identified by **location + run id**. Each root has a
> stable `root_id` (a hash of its path), and a run's full identity is
> `<root_id>:<run_id>`. Bare run ids resolve against the primary root first, so
> existing links keep working; the `?root=<root_id>` query param disambiguates
> the rare case where the same name/run id exists in more than one root.

---

## Long-running analysis runs — detach & reattach

Clicking **Run** on a config (or POSTing to `/api/runs/from-config`) now
spawns `fmriflow run <config.yaml>` as a detached subprocess
(`start_new_session=True`) with stdout+stderr captured to
`~/.fmriflow/runs/{run_id}/stdout.log` and a sidecar `state.json`. The
analysis subprocess survives server restarts the same way preproc,
convert, and autoflatten do.

On server startup, `RunManager._reattach_active_runs` scans the registry
and re-registers any live pipeline PIDs. They show up in the In-Flight
Analysis Runs panel at the top of the Dashboard right pane with a
`REATTACHED` tag.

### HTTP API

```bash
# List active + recent in-flight runs
curl http://localhost:8000/api/runs/in-flight

# Summary + last 200 log lines for one run
curl http://localhost:8000/api/runs/in-flight/abc123def456

# Cancel a running pipeline
curl -X POST http://localhost:8000/api/runs/in-flight/abc123def456/cancel
```

### Outcome inference

On reattach (PID-dead check), the monitor looks for
`{output_dir}/run_summary.json` — present → `done` (and the Run History
row appears on next Dashboard refresh); missing → `failed`.

### Tradeoff

Because the pipeline now runs in a child process, the structured stage
events that the in-process `UICaptureProxy` used to emit no longer reach
the server's WebSocket. The live log stream in the Log modal and In-Flight
panel is still there, and the full stage timeline + artifacts show up in
Run History once the pipeline writes its `run_summary.json`. If you need
mid-run per-stage progress in the dashboard, we can add a JSON-lines
event file the subprocess writes to — ask.

## Keyboard shortcuts and tips

- The sidebar auto-expands the group containing the active page
- Click the logo to return to the Dashboard from any view
- All long-running operations (conversions, preprocessing, pipeline runs) stream progress via WebSocket — you see results in real time
- Batch conversion configs saved through the UI are valid YAML files that work with `fmriflow convert batch --config`
