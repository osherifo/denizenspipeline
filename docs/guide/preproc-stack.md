# Preprocessing pipelines (stack)

The **Preproc (stack)** page composes a preprocessing pipeline
from two kinds of building block: one **bootstrap stage** that
takes raw BIDS to an initial manifest, plus zero or more
**transforms** that consume the prior stage's outputs and emit
updated ones. Outputs are cached by fingerprint, so re-running
with unchanged params is a no-op.

This page replaces the older single-backend "Preproc" launch
form. The legacy page now serves only as a read-only browser
for manifests, backend status, and collecting existing outputs.

## At a glance

```
┌── Stage 0 · Bootstrap ──────────────────────────────────┐
│  Backend: fmriprep | nipype | custom | bids_app |       │
│           passthrough                                    │
│  Workflow: identity (nipype only)                        │
│  Params: schema-driven form (or JSON fallback)           │
│  Preflight: ready / N errors                             │
└──────────────────────────────────────────────────────────┘

⋮⋮  Stage 1 · smooth (drag handle)
⋮⋮  Stage 2 · regress_confounds
⋮⋮  Stage 3 · …

[+ Add transform...]

[Run pipeline] [Cancel]

Live events:
  ▶ run started · subject=sub01 · 4 stages
  ✓ stage 0 (bootstrap): fmriprep done 482.13s
  ✓ stage 1 (transform): smooth done 8.47s (cache hit)
  ...
```

## Bootstrap kinds

| Kind          | When to use                                                                                  |
|---------------|----------------------------------------------------------------------------------------------|
| `fmriprep`    | Standard turnkey preprocessing. Wraps the existing fmriprep backend (Docker / Singularity). |
| `nipype`      | Choose a registered nipype workflow (the built-in `identity` no-op, or your own).            |
| `custom`      | Shell-command template you supply via `params.command`.                                       |
| `bids_app`    | Any other BIDS-App container (mriqc, etc.).                                                   |
| `passthrough` | Data is already preprocessed elsewhere; scan `derivatives_dir` and emit a manifest.          |

When you pick `nipype`, a second dropdown lists registered
workflows. The built-in `identity` is a no-op for testing.
The dropdown also includes a `＋ Author custom workflow...`
entry that opens a Python editor and drops your workflow into
`$FMRIFLOW_HOME/addons/workflows/`.

## Built-in transforms

| Name                | What it does                                                                  |
|---------------------|-------------------------------------------------------------------------------|
| `smooth`            | Isotropic Gaussian smoothing via `scipy.ndimage`. Param: `fwhm` (mm).         |
| `mask_apply`        | Zero voxels outside a binary mask. Inputs: `in_file`, `mask_file`.            |
| `regress_confounds` | Per-voxel OLS regression of nuisance columns from a BIDS-derivatives TSV.     |
| `identity`          | Passthrough — useful for testing the pipeline end-to-end without real work.   |

Custom transforms are authored from the `＋ Author custom
transform...` entry in the picker (drops a `.py` file into
`$FMRIFLOW_HOME/addons/transforms/`) — or by writing the file
directly and hitting `POST /api/preproc/backends/rescan`.

## Caching + "Run from here"

Each stage gets a fingerprint computed from its config + inputs.
Bootstrap fingerprints include a recursive `(path, mtime, size)`
hash of the BIDS subject directory; transform fingerprints
include the prior stage's fingerprint so any upstream change
cascades downstream automatically.

A second run with identical params hits the cache and skips
execution. Visually, the stage card shows a `cached` badge.

Click the **▶ from here** button on any transform card to force
re-execution of that stage onward, even when the cache would
hit. Useful when something external changed (a confounds file
edited out-of-band, the BIDS mtime hash missed something) and
you want to be sure.

The `Use cache` checkbox in the Run Controls disables caching
entirely for the run.

## Presets

The bottom panel saves the current stack (recipe only — no
subject binding) as a named YAML file in
`$FMRIFLOW_HOME/addons/pipelines/`. Reload across subjects, share
across labs by committing the YAML to a shared dir or pip
package.

## Custom workflows + transforms

Two paths today:

1. **In-app editor.** `＋ Author custom workflow...` /
   `＋ Author custom transform...` open a modal with a starter
   scaffold and a textarea. Save writes to
   `$FMRIFLOW_HOME/addons/{workflows,transforms}/<slug>.py` and
   rescans the registry so the new entry appears in the
   dropdown immediately. Code is syntax-checked
   (`compile()`) before save.
2. **Drop a Python file in by hand.** Write your
   `@register_preproc_workflow("name")` / `@register_transform("name")`
   class anywhere under `$FMRIFLOW_HOME/addons/workflows/` or
   `addons/transforms/`, then `POST /api/preproc/backends/rescan`
   (or restart the server).

The Protocol for either is documented at the top of
`fmriflow/preproc/preproc_workflow.py` and
`fmriflow/preproc/transform.py`. A visual ReactFlow builder is
planned but not yet shipped.

## Running

The **Run Controls** panel binds the stack to a specific subject
and output dir. Required: `subject` and `output_dir`. For
`passthrough` bootstrap, `derivatives_dir` is also required.

Click **Run pipeline** — the subprocess runs detached and
survives server restart. Live events stream over WebSocket;
cancel sends SIGTERM with a grace-period SIGKILL.

The **Recent runs** panel below lists every stack run on disk.
Click any row to load that run's status into the active panel
(stages show cached/done/failed badges derived from the run's
recorded `stage_cache_hits`).

## Migrating from the legacy Preproc page

The launch surface on the old page (Run / Configs tabs) has been
removed. If you were using saved preproc YAML configs:

- Open the new **Preproc (stack)** page.
- Compose the equivalent stack by selecting your backend kind +
  copying the params over to the schema-driven form.
- Save the result as a preset to reuse across subjects.

The legacy page is still useful for:

- Browsing existing fmriprep manifests on disk.
- Checking backend availability.
- Collecting existing preprocessed outputs into a manifest.
- Watching any in-flight fmriprep jobs that were launched before
  the migration.

## API endpoints

The stack page is backed by:

| Method | Path                                                  | Purpose                                    |
|--------|-------------------------------------------------------|--------------------------------------------|
| GET    | `/api/preproc/backends/workflows`                     | List registered workflows.                 |
| GET    | `/api/preproc/backends/workflows/{name}/preflight`    | REQUIRED_* check before launch.            |
| POST   | `/api/preproc/backends/workflows/custom`              | Save a custom workflow Python file.        |
| GET    | `/api/preproc/backends/transforms`                    | List registered transforms.                |
| GET    | `/api/preproc/backends/transforms/{name}/preflight`   | Same for transforms.                       |
| POST   | `/api/preproc/backends/transforms/custom`             | Save a custom transform Python file.       |
| POST   | `/api/preproc/backends/rescan`                        | Re-discover both registries.               |
| POST   | `/api/preproc/stack/run`                              | Launch a detached stack run.               |
| GET    | `/api/preproc/stack/runs`                             | List runs.                                 |
| GET    | `/api/preproc/stack/{run_id}/status`                  | Live status + result payload.              |
| GET    | `/api/preproc/stack/{run_id}/manifest`                | Final `PreprocManifest` JSON.              |
| POST   | `/api/preproc/stack/{run_id}/cancel`                  | SIGTERM the run.                           |
| GET    | `/api/preproc/stack/presets`                          | List saved presets.                        |
| POST   | `/api/preproc/stack/presets`                          | Save the current stack as a preset.        |
| GET    | `/api/preproc/stack/presets/{name}`                   | Load a preset.                             |
| DELETE | `/api/preproc/stack/presets/{name}`                   | Delete a preset.                           |
| WS     | `/ws/preproc/stack/{run_id}`                          | Live event stream.                         |
