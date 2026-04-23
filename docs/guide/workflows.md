# Workflows — End-to-End Pipelines

Workflows string together the four stage pipelines (DICOM → BIDS,
preprocessing, autoflatten, analysis) into a single ordered execution
driven by one YAML file. Each stage entry references an existing
stage-config YAML that already lives under
`./experiments/<stage>/` — the workflow YAML is a manifest, not a
duplicate of stage config bodies.

## YAML schema

```yaml
workflow:
  name: AN reading (en) — full pipeline
  subject: AN   # optional, for display

  stages:
    - stage: convert
      config: experiments/convert/an_reading_en.yaml
    - stage: preproc
      config: experiments/preproc/fmriprep_AN.yaml
    - stage: autoflatten
      config: experiments/autoflatten/AN.yaml
    - stage: analysis
      config: experiments/mkr_AN.yaml
```

- `stages[].stage` must be one of `convert`, `preproc`, `autoflatten`, `analysis`.
- `stages[].config` is a path to an existing stage YAML. Relative paths resolve against the workflow YAML's parent dir first, then against the server's cwd.
- Stages run **in list order**, one at a time, stop-on-first-failure.
- You can omit any stage — a workflow can be just `preproc → analysis` if convert isn't needed.

## Where YAMLs live

The workflow config store scans `./experiments/workflows/`. Same pattern as the other four stages:
- `./experiments/` — analysis
- `./experiments/preproc/`
- `./experiments/convert/`
- `./experiments/autoflatten/`
- `./experiments/workflows/` — **this page**

## Running

### Dashboard

Sidebar → **Pipeline → Workflows** → click a config → **Run**. The page shows:

- **Workflow Runs** panel at the top — every recent run with per-stage status (`pending / running / done / failed`) collapsed into one line, plus a Cancel button for live runs.
- **Detail pane** (when a run is selected) — a stage strip with one card per stage showing status, child run_id, and any error.
- **Configs list** on the left, detail + Run button on the right.

### HTTP API

```bash
# List workflow configs
curl http://localhost:8000/api/workflows/configs

# Get one
curl http://localhost:8000/api/workflows/configs/an_reading_en_full.yaml

# Start it
curl -X POST http://localhost:8000/api/workflows/configs/an_reading_en_full.yaml/run

# List active + recent runs
curl http://localhost:8000/api/workflows/runs

# Get per-stage status for one run
curl http://localhost:8000/api/workflows/runs/workflow_abc123def456

# Cancel (SIGTERM to the current stage's child subprocess via the stage manager)
curl -X POST http://localhost:8000/api/workflows/runs/workflow_abc123def456/cancel
```

## How orchestration works

The `WorkflowManager` runs one background thread per active workflow. For each stage it:

1. Calls the stage manager's `start_run_from_config_file(path)` — the same entry point the individual stage tabs use.
2. Polls the stage manager's `active_runs` (or `active_batches`, for convert) every 2 s until the child handle transitions out of `running`.
3. On `done`, advances to the next stage. On anything else, marks the whole workflow failed and stops.

Each child run keeps its own **detach/reattach** machinery from earlier — individual stage subprocesses survive server restarts.

## Caveats

- **No workflow-level reattach across server restarts.** If the server dies mid-workflow, the current stage's subprocess keeps running (via stage-level detach) but the workflow's "kick off the next stage when this one finishes" intent is lost. The child run still finishes correctly and shows up in its own stage tab; you just have to start the next stage manually.
- **Sequential only.** No parallel stages. If you want to run the same workflow for many subjects in parallel, define one workflow YAML per subject and run them independently.
- **Stop-on-failure.** No `continue_on_failure` per stage yet.
- **Workflow state is derived, not authoritative.** The source of truth for each stage is still its own `run_summary.json` / `preproc_manifest.json` / etc. The workflow just orchestrates — it doesn't duplicate results.
