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

# Run on the stage orchestrator instead of the graph engine
fmriflow run experiment.yaml --engine legacy

# Run an analysis graph file, giving its inputs
fmriflow run analysis.yaml --input subject=sub01 --input output_dir=/data/results/sub01

# Validate config without running
fmriflow validate experiment.yaml
```

### Engines

Subject runs use the graph engine: the stage config is compiled into a graph of nodes, one per module,
and run in-process. It writes the run summary, events, intermediates and reports, plus `graph.json` with
the executed graph. `--engine legacy` or `FMRIFLOW_ENGINE=legacy` runs the stage orchestrator instead.
`--stages` and `--resume-from` need the stage orchestrator and switch to it automatically unless
`--engine graph` was given.

### Analysis graphs

```bash
# Compile a stage config into the equivalent graph
fmriflow graph compile experiment.yaml -o analysis.yaml

# Check a graph (or the graph a stage config compiles to) without running it
fmriflow graph validate analysis.yaml --input subject=sub01
```

See [Analysis graphs](analysis-graphs.md) for the file format.

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
`--engine legacy` runs a group or study on the stage orchestrators instead of the graph engine; see
[Group Analysis](group-analysis.md#engines).
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
