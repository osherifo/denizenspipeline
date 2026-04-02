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

Heuristics are Python files that tell heudiconv how to map DICOM series to BIDS filenames. They live in `~/.denizens/heuristics/`.

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

Conversion configs can be saved for reproducibility and re-use:

- **Web UI:** "Save Config" button on the Batch form
- Configs are stored as YAML in `~/.denizens/convert_configs/`
- Saved configs are valid batch YAML files — usable directly with `fmriflow convert batch --config`

## Web UI

The DICOM-to-BIDS tab in the web UI provides:

- **Single run form** — fill in subject, session, source dir, heuristic, run
- **Batch form** — editable jobs table with shared settings, load/export YAML
- **Live progress** — per-job status badges, streaming logs, elapsed time
- **Saved configs** — save, load, and delete conversion configs
