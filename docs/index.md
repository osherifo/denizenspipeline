# fMRIflow

Plugin-based pipeline for voxelwise encoding models. Config-driven, modular architecture.

## What it does

fMRIflow takes stimulus data (text, audio, video) and fMRI brain responses, extracts features from the stimuli, fits encoding models (ridge regression), and reports prediction accuracy — all driven by a YAML config file.

```yaml
experiment: my_reading_study
subject: sub01
features:
  - name: numwords
  - name: english1000
split:
  test_runs: [story01]
```

```bash
fmriflow run experiment.yaml
```

## Key features

- **Config-driven** — one YAML file defines the entire experiment
- **Plugin architecture** — feature extractors, preparers, models, and reporters are all swappable
- **Web UI** — browser-based pipeline composer, DICOM-to-BIDS conversion, run manager
- **DICOM to BIDS** — heudiconv integration with heuristic registry and batch conversion
- **fMRI preprocessing** — fmriprep wrapper with manifest-based provenance tracking
- **Surface flattening** — autoflatten integration with pycortex import
- **Visual workflow builder** — node-based pipeline graph with bidirectional YAML sync
- **Incremental runs** — run stages independently, resume from checkpoints

## Quick install

```bash
cd fmriflow
pip install -e .

# With optional extras
pip install -e ".[nlp]"      # transformers, gensim
pip install -e ".[viz]"      # pycortex flatmaps
pip install -e ".[all]"      # everything
```

## Next steps

- [Installation](guide/installation.md) — full install options and environment setup
- [Quickstart](guide/quickstart.md) — write your first experiment config and run it
- [CLI Reference](guide/cli.md) — all available commands
- [Writing Plugins](guide/plugins.md) — extend the pipeline with custom extractors, models, and reporters
- [Autoflatten](guide/autoflatten.md) — cortical surface flattening + pycortex import
- [Pipeline Graph](guide/pipeline-graph.md) — visual workflow builder with YAML sync
