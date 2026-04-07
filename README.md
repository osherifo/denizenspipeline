# fMRIflow

![Version](https://img.shields.io/badge/version-2.0.0--alpha.2-blue)
![Python](https://img.shields.io/badge/python-≥3.10-green)
![License](https://img.shields.io/badge/license-MIT-brightgreen)

Plugin-based pipeline for voxelwise encoding models. Config-driven, modular architecture for fMRI experiments — from DICOM conversion through feature extraction, model fitting, and reporting.

## Install

```bash
pip install -e .
pip install -e ".[all]"    # with all optional extras
```

## Quickstart

```yaml
# experiments/my_experiment.yaml
experiment: my_reading_study
subject: sub01
features:
  - name: numwords
  - name: english1000
split:
  test_runs: [story01]
```

```bash
fmriflow run experiments/my_experiment.yaml
```

## Documentation

- [Installation](docs/guide/installation.md) — install options and environment setup
- [Quickstart](docs/guide/quickstart.md) — write your first experiment config
- [Configuration](docs/guide/configuration.md) — config format, inheritance, env vars
- [CLI Reference](docs/guide/cli.md) — all commands
- [Python API](docs/guide/python-api.md) — programmatic usage and notebooks
- [Writing Plugins](docs/guide/plugins.md) — custom extractors, models, reporters
- [Preprocessing](docs/guide/preprocessing.md) — fmriprep integration and manifests
- [DICOM to BIDS](docs/guide/dicom-to-bids.md) — conversion and batch processing
- [Built-in Plugins](docs/reference/plugins.md) — full plugin list
- [Config Reference](docs/reference/config.md) — complete config schema
- [Defaults](docs/reference/defaults.md) — default values for all settings

### Build the docs

Install the documentation dependencies and serve or build locally:

```bash
pip install mkdocs-material pymdown-extensions
mkdocs serve   # live-reload dev server at http://127.0.0.1:8000
mkdocs build   # static site output in site/
```
