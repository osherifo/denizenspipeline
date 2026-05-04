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
- **Detail pane** — auto-opens on the most recent running workflow (or the newest finished one if nothing's in-flight) so you see progress immediately without clicking into a row. A ReactFlow graph shows one node per stage, connected left-to-right: the currently running stage pulses cyan; edges animate between `done` and `running` neighbours; failed stages and the edge leading out of them are red. Each node shows the stage name, status badge, config filename, elapsed time, and child `run_id`. **Clicking a stage node with a child run** opens a log modal with metadata + the last 200 lines of that child's `stdout.log`, auto-refreshed every 3 s while running. The modal routes to the correct stage endpoint based on the stage type — `/convert/runs/*`, `/preproc/runs/*`, `/autoflatten/runs/*`, `/runs/in-flight/*` — so logs are never more than one click away from the workflow view. When the convert stage ran as a batch (the id starts with `batch_`), the modal shows a per-job summary first with status counts and a row per job; clicking a job opens that individual run's log and a ← Batch button returns to the list.

**The analysis node decomposes into its inner stages.** When the analysis stage has a child run, its node in the graph shows a 7-pill strip at the bottom covering the pipeline's canonical sub-stages — `stimuli / responses / features / prepare / model / analyze / report`. Each pill is colored by status (pending grey, running cyan, ok green, warning yellow, failed red). The running pill gets a filled background so you can see progression inside the analysis stage at a glance. Data comes from a JSON-lines events file the analysis subprocess writes to `~/.fmriflow/runs/{run_id}/events.jsonl` (see `fmriflow.ui._emit_event`), which the server parses into a stage list on the `/api/runs/in-flight/{run_id}` response. The workflow view polls it every 2 s while analysis is running.

**Below the graph**, a **live log pane** auto-tails the currently active stage's `stdout.log` (polled every 2.5 s while running). The active stage is resolved as: first running stage → else first failed stage → else last stage with a child run_id — so something useful shows up after a failure or completion too. For convert batches the pane drills into a single job automatically (prefers running, else failed, else the last one that actually spawned). An auto-scroll toggle pins the view to the tail; the **Open full log** button pops the same StageLogModal for when you want the full summary + Copy.
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

### Live nipype-node monitoring (Preproc stage)

When the Preproc stage runs **fmriprep**, the Workflows view tails its
stdout for nipype's `[Node]` lines and surfaces a per-node status
strip under the Preproc block. Each node renders as a small pill
colored by status (cyan = running, green = ok, red = failed) and
grouped by the top two segments of its workflow path
(`fmriprep_wf.bold_preproc_wf`, `fmriprep_wf.sdc_estimate_wf`, …).

The strip is **default-collapsed** with a one-line summary
(`3 running / 47 done / 1 failed · 51 seen`); click the chevron to
expand. Hovering a pill shows the full dotted node path and elapsed
seconds.

Behind the scenes:

- `_LogTailer` already streams stdout line by line. Each line is
  also fed to a small stateful parser
  (`fmriflow/preproc/nipype_log.py::NipypeLogParser`) that emits
  `node_start`, `node_done`, `node_fail` events.
- Events are appended to
  `~/.fmriflow/runs/{run_id}/nipype_events.jsonl`.
- The frontend polls
  `GET /api/preproc/runs/{run_id}/live` every 2 s while the stage
  is running; the response includes a `nipype_status` block built
  by re-parsing the JSONL.
- The JSONL on disk is the source of truth, so the strip
  rehydrates after a server restart / detach-reattach.

This is **log-tailing only** — no fmriprep monkey-patching, no nipype
plugin shim. If the log format ever drifts, unmatched lines are
dropped and the rest of the strip keeps working. A richer
status-callback shim is sketched in
`devdocs/proposals/frontend/live-fmriprep-node-monitoring.md` as a
future v2.

#### Drill-in: the live nipype DAG

**Double-click** the Preproc block (when its strip has at least one
node) to open a full-screen ReactFlow view of the live nipype graph,
laid out top-to-bottom by `dagre`. Each leaf is a real nipype node
(colored by status, with elapsed seconds); each parent is a virtual
summary box for a sub-workflow that rolls up `running / done / failed`
counts of its descendants.

The modal polls the same `/api/preproc/runs/{run_id}/live` endpoint as
the strip and re-lays out on each refresh. Once the run finishes, the
DAG remains viewable from the saved JSONL — useful for postmortems on
failed runs ("which sub-workflow blew up?"). v1 derives the DAG from
the dotted node paths nipype prints, not from a real dependency graph
— so it shows hierarchy, not data flow. A real-DAG view requires the
status-callback shim in v2.

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
