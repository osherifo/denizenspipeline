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

For container-based runs (Singularity):

```bash
conda install conda-forge::singularity
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

## Workflow 2: Run preprocessing

```bash
fmriflow preproc run --config preproc_config.yaml
```

Config format:

```yaml
preproc:
  backend: fmriprep
  bids_dir: /data/bids/my_study/
  output_dir: /data/derivatives/fmriprep/
  subject: sub01
  task: reading
  sessions: [session01]

  backend_params:
    container: /images/fmriprep-23.2.1.sif
    container_type: singularity
    output_spaces: [T1w]
    fs_license_file: ~/.freesurfer/license.txt

  confounds:
    strategy: motion_24
    high_pass: 0.01

  run_map:
    run-01: story01
    run-02: story02
```

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
