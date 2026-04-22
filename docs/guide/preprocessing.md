# fMRI Preprocessing

A standalone module for managing fMRI preprocessing (fmriprep, custom scripts, BIDS-Apps). It produces a `PreprocManifest` — a JSON contract between preprocessing and the analysis pipeline — providing provenance tracking, validation, and reproducibility.

## Environment setup

fMRIPrep has heavy dependencies, so install fMRIflow into the conda env that already has fmriprep:

```bash
# Option A: install the pipeline into your fmriprep env (recommended)
conda activate fmriprep-py310
cd fmriflow
pip install -e .

# Option B: install fmriprep into the pipeline env
conda activate fmriflow
pip install fmriprep
```

For container-based runs (Singularity or Apptainer):

```bash
conda install conda-forge::apptainer    # preferred — modern fork
# or: conda install conda-forge::singularity
```

The fmriprep backend resolves the container runtime in this order:

1. `$FMRIFLOW_SINGULARITY_BIN` (absolute path, if set)
2. `apptainer` on PATH
3. `singularity` on PATH

If your environment ships an old Singularity 2.x that can't run current
fmriprep images, install Apptainer into a dedicated conda env and point
the server at its binary:

```bash
FMRIFLOW_SINGULARITY_BIN=$HOME/miniconda3/envs/dv2/bin/apptainer fmriflow serve
```

Pull an fmriprep image once and point your configs at the `.sif`:

```bash
apptainer pull ~/images/fmriprep/fmriprep_25.1.3.sif docker://nipreps/fmriprep:25.1.3
```

You also need a FreeSurfer license file:

```bash
export FS_LICENSE=~/fmriprep-local/fs_license.txt
```

## Quick check

```bash
fmriflow preproc doctor
```

## Workflow 1: Register existing outputs

If you already ran fmriprep and want to hook the outputs into the pipeline:

```bash
# Build a manifest from existing fmriprep derivatives
fmriflow preproc collect \
  --backend fmriprep \
  --output-dir /data/derivatives/fmriprep/ \
  --subject sub01 \
  --task reading \
  --run-map '{"run-01": "story01", "run-02": "story02"}'

# Inspect and validate
fmriflow preproc info manifest.json
fmriflow preproc validate manifest.json
```

Then point your analysis config at the manifest:

```yaml
response:
  loader: preproc
  manifest: /data/derivatives/fmriprep/sub-sub01/preproc_manifest.json
  mask_type: thick
```

## Workflow 2: Run preprocessing from a YAML config

The same YAML drives three equivalent entry points: CLI, HTTP API, and the
dashboard's **Configs** tab. Put the file anywhere for CLI use, or under
`./experiments/preproc/` so the dashboard and API auto-discover it.

### Config format

```yaml
preproc:
  backend: fmriprep
  bids_dir: /data/bids/my_study/
  output_dir: /data/derivatives/fmriprep/
  work_dir: /data/derivatives/work/
  subject: sub01
  task: reading
  sessions: [session01]

  backend_params:
    # Container
    container: /images/fmriprep/fmriprep_25.1.3.sif
    container_type: singularity         # also runs under Apptainer — see above

    # Mode: full | anat_only | func_only | func_precomputed_anat
    mode: func_only                     # skips FreeSurfer reconall

    # FreeSurfer license (required for full / func_precomputed_anat)
    fs_license_file: ~/.freesurfer/license.txt

    # Output spaces
    output_spaces:
      - MNI152NLin2009cAsym:res-2
      - T1w

    # Resources
    nthreads: 12
    omp_nthreads: 8
    mem_mb: 32000

    # Bypass the in-container BIDS validator for datasets that intentionally
    # deviate from strict BIDS.
    skip_bids_validation: true

  confounds:
    strategy: motion_24
    high_pass: 0.01

  run_map:
    run-01: story01
    run-02: story02
```

The backend auto-creates `output_dir` and `work_dir` before launching —
Apptainer refuses to bind-mount paths that don't exist on the host.

### 2a. Run from the CLI

```bash
fmriflow preproc run --config experiments/preproc/my_config.yaml
```

### 2b. Run from the dashboard (Preprocessing → Configs)

The dashboard scans `./experiments/preproc/*.yaml` for files with a top-level
`preproc:` section and lists them in the **Configs** tab. Clicking a config
shows its summary (subject, backend, container, mode, paths) and the raw YAML,
with a **Run** button that starts the job and streams live fmriprep output
into the progress panel below.

### 2c. Run via HTTP API

```bash
# List discovered configs
curl http://localhost:8000/api/preproc/configs

# Get one
curl http://localhost:8000/api/preproc/configs/my_config.yaml

# Kick off a run (body is optional — any fields shallow-merge onto the YAML)
curl -X POST http://localhost:8000/api/preproc/configs/my_config.yaml/run \
  -H 'Content-Type: application/json' \
  -d '{"subject": "sub02"}'
```

The response returns a `run_id` you can use to tail live events over
`/ws/preproc/{run_id}`.

## Long-running jobs — detach & reattach

fmriprep runs take hours. To let you close the browser, restart the server,
or reboot the machine without killing a job in progress, fmriprep jobs
launched through the dashboard or `/api/preproc/configs/{file}/run` are
detached from the server process:

- The fmriprep subprocess is spawned in its own process group
  (`start_new_session=True`), so it survives if the parent dies.
- stdout+stderr go straight to a log file under
  `~/.fmriflow/runs/{run_id}/stdout.log` — never to a broken pipe.
- A sidecar `state.json` in the same directory records pid, pgid, start
  time, config path, and current status.

When the server restarts it scans `~/.fmriflow/runs/*/state.json`:

- Any run marked `running` whose PID is still alive is re-registered.
  Its progress is reconstructed by tailing the existing `stdout.log`,
  and a `REATTACHED` tag appears next to it in the UI.
- If the PID is dead, the run is marked `lost` so the history view
  doesn't show an eternal "running."
- Finished runs stay on disk for inspection; no auto-delete.

### UI

In the Preprocessing → Configs tab a new **In Flight** panel at the top
lists running jobs (plus recent completions). Each row has:

- `Watch` — opens the live progress panel and starts streaming from the
  log file via WebSocket.
- `Cancel` — `SIGTERM` the process group; `SIGKILL` after a 5-second grace
  period.

### HTTP API

```bash
# List all runs (in-memory + on-disk)
curl http://localhost:8000/api/preproc/runs

# Get summary + last 200 log lines for one
curl http://localhost:8000/api/preproc/runs/preproc_AH_4f2b9c1a

# Cancel a running job
curl -X POST http://localhost:8000/api/preproc/runs/preproc_AH_4f2b9c1a/cancel
```

### Caveats

- Only the `fmriprep` backend is detached. `custom` and `bids_app` still
  run in-process and will be killed if the server dies.
- The subprocess's exit code is only known to the server that spawned
  it. Reattached runs infer outcome by checking for fmriprep's HTML
  report in the output dir — present → `done`, missing → `failed`.
- If you're running under Docker, bind-mount `~/.fmriflow` to the host
  so the runs directory survives container restarts.

## Workflow 3: Custom script

```bash
fmriflow preproc run \
  --backend custom \
  --raw-dir /data/raw/sub01/ \
  --output-dir /data/preprocessed/sub01/ \
  --subject sub01 \
  --command "python my_preproc.py --subject {subject} --input {input_dir} --output {output_dir}"
```

## Confound regression

Apply confound regression when the analysis pipeline loads the data:

```yaml
response:
  loader: preproc
  manifest: manifest.json
  confounds:
    strategy: motion_24    # or: motion_6, acompcor, custom
    high_pass: 0.01
    fd_threshold: 0.5      # scrub high-motion TRs
```

Available strategies:

- `motion_24` — 6 motion params + derivatives + squared + squared derivatives
- `motion_6` — 6 motion params only
- `acompcor` — 6 motion params + 5 anatomical CompCor components
- `custom` — specify exact column names with `columns: [col1, col2, ...]`

## Backends

| Backend | Use case |
|---------|----------|
| `fmriprep` | Wraps fmriprep (bare, Singularity, or Docker) |
| `custom` | Runs any shell command with `{subject}`, `{input_dir}`, `{output_dir}` placeholders |
| `bids_app` | Generic BIDS-App wrapper (any container following the standard CLI) |

## The manifest

`preproc_manifest.json` records everything about preprocessing: backend, version, parameters, output space, confounds, per-run QC metrics (framewise displacement, tSNR), and file paths. The analysis pipeline validates this before loading data, catching mismatches early.
