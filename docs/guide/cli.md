# CLI Reference

## Pipeline

```bash
# Run full pipeline
fmriflow run experiment.yaml

# Run specific stages
fmriflow run experiment.yaml --stages features,prepare,model

# Resume after a checkpointed stage (needs `checkpoint: true` in the config);
# only the stages after `features` run
fmriflow run experiment.yaml --resume-from features

# Dry run (show what would execute)
fmriflow run experiment.yaml --dry-run

# Run on the node-graph engine instead of the stage orchestrator
fmriflow run experiment.yaml --engine graph

# Validate config without running
fmriflow validate experiment.yaml
```

### Engines

`--engine graph` compiles the stage config into a graph of nodes, one per module, and runs it in-process.
It writes the same run summary, events, intermediates and reports as the default stage orchestrator, plus
`graph.json` with the executed graph. Set `FMRIFLOW_ENGINE=graph` to make it the default. The graph engine
always runs the whole pipeline, so `--stages` and `--resume-from` still need `--engine legacy`.

## Group and study runs

```bash
# Run a group (subjects) or a study (groups)
fmriflow run-group group.yaml
fmriflow run-study study.yaml

# Continue the most recent run: subjects whose run_summary.json is ok are skipped
fmriflow run-group group.yaml --resume

# Write to (or continue) a specific run directory
fmriflow run-group group.yaml --resume --run-id 20260911T101500Z
```

Each run writes to `<output_dir>/<run_id>/`, with a `latest` link to the newest run.
Subject modules from your add-on directory load for these commands too.

## Modules

```bash
# List all modules (by category)
fmriflow list modules

# List modules for a specific stage
fmriflow list prepare
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
# Preflight every node in the library (tools, env vars, python deps)
fmriflow preproc doctor

# Run a pipeline: a saved pipeline name, a template name, or a pipeline YAML
fmriflow preproc run fmriprep_anat_only --subject 01 \
  --bids-dir ./testing/my_study/bids --output-dir ./testing/my_study/derivatives \
  --param fmriprep.output_spaces='["T1w"]'
fmriflow preproc run my_pipeline.yaml --subject 01 --output-dir ./out \
  --derivatives-dir /data/derivatives --rerun-from smooth --no-cache

# Build a manifest from existing fmriprep outputs (no run)
fmriflow preproc collect \
  --backend fmriprep \
  --output-dir /data/derivatives/fmriprep/ \
  --subject sub01 \
  --task reading \
  --run-map '{"run-01": "story01", "run-02": "story02"}'

# Inspect / validate a manifest
fmriflow preproc info /data/derivatives/fmriprep/sub-sub01/preproc_manifest.json
fmriflow preproc validate /data/derivatives/fmriprep/sub-sub01/preproc_manifest.json
fmriflow preproc validate manifest.json --for-config experiments/my_experiment.yaml

# Convert old stack presets / post-preproc graphs / backend-style configs into pipelines
fmriflow preproc migrate --dry-run
fmriflow preproc migrate --workflows-dir ./experiments/workflows
```

## Server

```bash
# Start the web UI
fmriflow serve
```
