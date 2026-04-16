# CLI Reference

## Pipeline

```bash
# Run full pipeline
fmriflow run experiment.yaml

# Run specific stages
fmriflow run experiment.yaml --stages features,preprocess,model

# Resume from a checkpoint
fmriflow run experiment.yaml --resume-from preprocess

# Dry run (show what would execute)
fmriflow run experiment.yaml --dry-run

# Validate config without running
fmriflow validate experiment.yaml
```

## Modules

```bash
# List all modules (by category)
fmriflow list modules

# List modules for a specific stage
fmriflow list preprocess
fmriflow list features
fmriflow list model

# List pipeline stages
fmriflow list
```

## DICOM to BIDS

```bash
# Single conversion
fmriflow convert run \
  --heuristic my_study \
  --subject sub01 \
  --session 01 \
  --source-dir /data/dicoms/session01/ \
  --bids-dir /data/bids/my_study/

# Batch conversion from YAML config
fmriflow convert batch --config batch_convert.yaml

# Batch dry run (show job table)
fmriflow convert batch --config batch_convert.yaml --dry-run

# Override parallelism
fmriflow convert batch --config batch_convert.yaml --parallel 2

# Scan DICOM directory
fmriflow convert scan /data/dicoms/session01/

# List available heuristics
fmriflow convert heuristics list

# Add a heuristic
fmriflow convert heuristics add my_heuristic.py

# Validate conversion output
fmriflow convert validate /data/bids/my_study/
```

## Preprocessing

```bash
# Check available backends
fmriflow preproc doctor

# Build manifest from existing fmriprep outputs
fmriflow preproc collect \
  --backend fmriprep \
  --output-dir /data/derivatives/fmriprep/ \
  --subject sub01 \
  --task reading \
  --run-map '{"run-01": "story01", "run-02": "story02"}'

# Run preprocessing
fmriflow preproc run --config preproc_config.yaml

# Inspect a manifest
fmriflow preproc info /data/derivatives/fmriprep/sub-sub01/preproc_manifest.json

# Validate a manifest
fmriflow preproc validate /data/derivatives/fmriprep/sub-sub01/preproc_manifest.json

# Validate against an analysis config
fmriflow preproc validate manifest.json \
  --for-config experiments/my_experiment.yaml
```

## Server

```bash
# Start the web UI
fmriflow serve
```
