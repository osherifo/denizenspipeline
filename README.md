# fMRIflow


![Version](https://img.shields.io/github/v/tag/osherifo/denizenspipeline?sort=semver&label=version&color=blue)
![Python](https://img.shields.io/badge/python-≥3.10-green)
![License](https://img.shields.io/badge/license-MIT-brightgreen)

Module-based pipeline for voxelwise encoding models. Config-driven, modular architecture for fMRI experiments — from DICOM conversion through feature extraction, model fitting, and reporting.

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

## Run with Docker

Two images, so you don't have to install fmriprep, FreeSurfer, heudiconv and the
frontend toolchain by hand:

| Variant | Size | Use when |
|---|---|---|
| **slim** | ~4 GB | The host already has Docker or apptainer, and fmriprep is delegated to it. |
| **full** | ~11 GB | You want one self-contained image — fmriprep, FreeSurfer and ANTs baked in. |

```bash
docker compose build                                    # slim
docker compose -f docker-compose.full.yml build         # full

# Point it at a working directory, then bring it up.
export FMRIFLOW_HOME=~/projects/fmriflow
PUID=$(id -u) PGID=$(id -g) docker compose up -d
```

The web UI is on <http://localhost:8421>. `$FMRIFLOW_HOME` is bind-mounted at
`/workspace`, so configs, runs and data live on the host and survive rebuilds.
Drop your FreeSurfer license at `$FMRIFLOW_HOME/secrets/freesurfer-license.txt`
(or set `FS_LICENSE_TEXT` to pass it inline).

In your preproc config, use `container_type: bare` on the full image, or
`container_type: docker` on slim to run fmriprep as a sibling container.

See the [Docker guide](docs/guide/docker.md) for the apptainer/HPC pattern,
splitting the data subtree onto another disk, and troubleshooting.

## Share artifacts

Modules, configs, heuristics, preproc-stack presets, error-KB entries and
precomputed feature arrays can be shared through the **Artifact Hub** — a
git-backed registry with local, within-lab, and curated community tiers. Open
the **Hub** tab.

To publish, add a source pointing at a git repo and give it a Personal Access
Token with **write** access (a classic PAT with the `repo` scope, or a
fine-grained PAT with Contents: Read and write — *not* a `gho_…` GitHub-CLI
token, which is short-lived):

- **Publish an artifact** — the picker at the top of the Hub page. Pick a source,
  a kind, and one of your local artifacts. This is also how you initialise an
  empty store. Choose **▸ All \<kind\>** to push everything of a kind in one
  commit.
- **Publish local** — on a catalog row, to push your version of an artifact the
  store already lists.

fMRIflow stages the file under `kinds/<kind>/`, regenerates the `hub.json`
manifest entry with its hash, commits, and pushes. Against a store that already
has content it pushes a **branch** and surfaces a PR link — that review is the
curation step. Only user-tier artifacts are publishable; a shipped builtin has
no local file to push.

```bash
pip install -e '.[hub]'    # optional: store the token in the OS keyring
```

See the [Artifact Hub guide](docs/guide/artifact-hub.md) for tiers, tokens, and
the store-repo contract.

## Documentation

- [Installation](docs/guide/installation.md) — install options and environment setup
- [Quickstart](docs/guide/quickstart.md) — write your first experiment config
- [Configuration](docs/guide/configuration.md) — config format, inheritance, env vars
- [CLI Reference](docs/guide/cli.md) — all commands
- [Python API](docs/guide/python-api.md) — programmatic usage and notebooks
- [Writing Modules](docs/guide/modules.md) — custom extractors, models, reporters
- [Preprocessing](docs/guide/preprocessing.md) — fmriprep integration and manifests
- [DICOM to BIDS](docs/guide/dicom-to-bids.md) — conversion and batch processing
- [Docker](docs/guide/docker.md) — slim and full images, working dir, apptainer/HPC
- [Artifact Hub](docs/guide/artifact-hub.md) — share modules, configs and heuristics
- [Built-in Modules](docs/reference/modules.md) — full module list
- [Config Reference](docs/reference/config.md) — complete config schema
- [Defaults](docs/reference/defaults.md) — default values for all settings

### Build the docs

Install the documentation dependencies and serve or build locally:

```bash
pip install mkdocs-material pymdown-extensions
mkdocs serve   # live-reload dev server at http://127.0.0.1:8000
mkdocs build   # static site output in site/
```
