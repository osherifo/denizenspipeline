# DICOM to BIDS

Convert raw DICOM data to BIDS format using heudiconv with a heuristic registry and batch conversion support.

## Single conversion

```bash
fmriflow convert run \
  --heuristic my_study \
  --subject sub01 \
  --session 01 \
  --source-dir /data/dicoms/session01/ \
  --bids-dir /data/bids/my_study/
```

## Batch conversion

For multi-subject, multi-session datasets, use a YAML config:

```yaml
# batch_convert.yaml
convert_batch:
  heuristic: my_study
  bids_dir: /data/bids/my_study/
  source_root: /data/dicoms/
  max_workers: 4
  validate_bids: true

  jobs:
    - subject: sub01
      session: "01"
      source_dir: sub01_session01/
    - subject: sub01
      session: "02"
      source_dir: sub01_session02/
    - subject: sub02
      session: "01"
      source_dir: sub02_session01/
```

```bash
# Run the batch
fmriflow convert batch --config batch_convert.yaml

# Dry run — see the job table without running
fmriflow convert batch --config batch_convert.yaml --dry-run

# Override parallelism
fmriflow convert batch --config batch_convert.yaml --parallel 2
```

Jobs run in parallel via a thread pool. The web UI shows live per-job progress with status badges and streaming logs.

## Heuristics

Heuristics are Python files that tell heudiconv how to map DICOM series to BIDS filenames. They live in `~/.fmriflow/heuristics/`.

```bash
# List available heuristics
fmriflow convert heuristics list

# Add a heuristic file
fmriflow convert heuristics add my_heuristic.py

# Get info about a heuristic
fmriflow convert heuristics info my_study
```

### Writing a heuristic

A heuristic file must define `infotodict(seqinfo)` which maps DICOM series info to BIDS path templates:

```python
"""
Heuristic file for my study.

Subjects: sub01, sub02, ...
Scanner: Siemens Prisma
"""
from collections import defaultdict


def infotodict(seqinfo):
    info = defaultdict(list)

    for s in seqinfo:
        sd = s.series_description.lower()

        if "t1w" in sd:
            template = "sub-{subject}/{session}/anat/sub-{subject}_{session}_T1w"
            info[(template, ("nii.gz",), None)].append(s.series_id)

        elif "bold" in sd:
            template = "sub-{subject}/{session}/func/sub-{subject}_{session}_task-rest_bold"
            info[(template, ("nii.gz",), None)].append(s.series_id)

    return dict(info)
```

!!! tip
    Always include `{session}` in BIDS paths when subjects have multiple sessions. Omitting it causes filename collisions across sessions.

## Saved configs

Conversion configs can be saved for reproducibility and re-use. The same
YAML drives three equivalent entry points: CLI, dashboard **Configs** tab,
and HTTP API.

- **Default location:** `./experiments/convert/` (project-local, discovered by the dashboard).
- **Legacy location:** `~/.fmriflow/convert_configs/` is still scanned read-only so pre-migration configs remain loadable — move them to `./experiments/convert/` when convenient.
- **Batch saved configs** are valid batch convert YAML files and can be used directly with `fmriflow convert batch --config <path>`.
- **Single-run saved configs** are not batch YAML files (they do not have top-level `jobs`), so run them from the dashboard **Configs** tab or via the HTTP API endpoint described below.

### Run from the dashboard (DICOM → BIDS → Configs)

The dashboard scans `./experiments/convert/*.yaml` and lists them in the
**Configs** tab. Clicking a config shows its summary + raw YAML with a
**Run** button that dispatches either a single or batch conversion based
on the file's shape (top-level `convert_batch:` or `jobs:` → batch,
otherwise single). Progress streams into the existing Convert / Batch
progress panel.

### Run via HTTP API

```bash
# List saved configs
curl http://localhost:8000/api/convert/configs

# Get one
curl http://localhost:8000/api/convert/configs/my_batch.yaml

# Kick off (body is optional — fields shallow-merge onto the YAML)
curl -X POST http://localhost:8000/api/convert/configs/my_batch.yaml/run
```

Returns `{"kind": "batch", "batch_id": ...}` or `{"kind": "single", "run_id": ...}`.

## Long-running conversions — detach & reattach

heudiconv runs spawned from the dashboard or `/api/convert/configs/{f}/run`
are detached from the server process: each subprocess lives in its own
process group (`start_new_session=True`) with stdout+stderr redirected to
`~/.fmriflow/runs/{run_id}/stdout.log`, and a `state.json` sidecar records
pid/status/timestamps. On server restart, live runs are re-registered and
show up in the **Recent Runs** panel at the top of the Configs tab with a
`REATTACHED` tag.

Batch jobs get the same treatment — each heudiconv subprocess inside a
batch is registered individually, so they survive server restarts. Batch
**grouping** is lost on reattach (the BatchRunHandle goes away); surviving
jobs re-appear as standalone convert runs in the Recent Runs panel.

### HTTP API

```bash
# List active + recent convert runs
curl http://localhost:8000/api/convert/runs

# Summary + last 200 log lines for one
curl http://localhost:8000/api/convert/runs/convert_AN_4f2b9c1a

# Cancel a running subprocess (SIGTERM → SIGKILL after 5s)
curl -X POST http://localhost:8000/api/convert/runs/convert_AN_4f2b9c1a/cancel
```

### Outcome inference

On reattach (PID-dead check), the monitor looks for
`{bids_dir}/convert_manifest.json` — present → `done` (manifest reloaded);
missing → `failed`. You can always re-run the manifest build from the
Collect tab if heudiconv finished but the parent died mid-collect.

## Web UI

The DICOM-to-BIDS tab in the web UI provides:

- **Single run form** — fill in subject, session, source dir, heuristic, run
- **Batch form** — editable jobs table with shared settings, load/export YAML
- **Configs** — browse saved YAMLs under `./experiments/convert/`, inspect their summary + YAML, Run directly
- **Recent Runs panel** (top of Configs tab) — lists active + finished runs with Log and Cancel buttons; survives server restarts via the detach/reattach machinery
- **Live progress** — per-job status badges, streaming logs, elapsed time
- **Saved configs** — save, load, run, and delete conversion configs
