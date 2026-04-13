# Deployment Guide

## Quick Start (Docker)

```bash
# Build the image
make build

# Start the web UI on http://localhost:8421
make serve

# Stop
make stop
```

## Quick Start (Singularity / HPC)

```bash
# Build .sif from Docker image (on a machine with Docker)
make sif
scp fmriflow.sif user@cluster:/images/

# Or pull directly on the cluster (no Docker needed)
singularity build fmriflow.sif docker://ghcr.io/osherifo/fmriflow:latest

# Run on the cluster
singularity exec --writable-tmpfs -B /data:/data fmriflow.sif \
    fmriflow run /data/experiments/config.yaml
```

---

## Docker

### Images

| Image | Build command | What's in it |
|-------|--------------|-------------|
| `fmriflow` | `make build` | Web UI, analysis pipeline, common Python deps |
| `fmriflow-full` | `make build-full` | Above + dcm2niix, autoflatten, cloud deps |

### Running the web UI

```bash
make serve          # starts on http://localhost:8421
make logs           # tail logs
make stop           # shut down
```

Or manually:

```bash
docker run --rm -p 8421:8421 \
    -v ./experiments:/data/experiments \
    -v ./results:/data/results \
    -v ./derivatives:/data/derivatives \
    fmriflow:latest
```

### Running pipeline commands

```bash
# Run an analysis pipeline
make run CONFIG=experiments/my_config.yaml

# Validate a config
make validate CONFIG=experiments/my_config.yaml

# Run preprocessing
make preproc ARGS="--backend fmriprep --subject sub01 --bids-dir /data/bids --output-dir /data/derivatives"

# Get a shell
make shell
```

### Volume mounts

| Host path | Container path | Purpose |
|-----------|---------------|---------|
| `./experiments` | `/data/experiments` | YAML experiment configs |
| `./results` | `/data/results` | Pipeline output (scores, flatmaps, summaries) |
| `./derivatives` | `/data/derivatives` | fmriprep / FreeSurfer outputs |
| `~/.denizens` | `/home/fmriflow/.denizens` | User plugins, heuristics, saved configs |

### Pushing to a registry

```bash
make push           # pushes fmriflow:latest to ghcr.io
make push-full      # pushes fmriflow-full:latest to ghcr.io
```

---

## Singularity / Apptainer (HPC)

### Building the .sif

```bash
# Option 1: From a local Docker build
make sif            # builds Docker image first, then converts to .sif

# Option 2: From the container registry (no Docker needed)
singularity build fmriflow.sif docker://ghcr.io/osherifo/fmriflow:latest

# Option 3: Full image with dcm2niix + autoflatten
make sif-full
```

### Running on a cluster

```bash
# Run a pipeline
singularity exec --writable-tmpfs -B /data:/data \
    fmriflow.sif fmriflow run /data/experiments/config.yaml

# With subject override
singularity exec --writable-tmpfs -B /data:/data \
    fmriflow.sif fmriflow run /data/experiments/config.yaml --subject sub01
```

**Important flags:**

| Flag | Purpose |
|------|---------|
| `--writable-tmpfs` | Writable temp space for matplotlib/pycortex caches |
| `-B /data:/data` | Bind mount your data directory |
| `-B $SCRATCH:/tmp` | Use cluster scratch for temp files |
| `--nv` | Enable GPU passthrough |

### Nested Singularity (fmriprep)

The pipeline calls fmriprep via Singularity. When the pipeline itself is in a Singularity container, this is Singularity-in-Singularity — which works natively:

```bash
singularity exec \
    --writable-tmpfs \
    -B /data:/data \
    -B /images:/images \
    fmriflow.sif \
    fmriflow preproc run \
        --backend fmriprep \
        --container /images/fmriprep-24.0.0.sif \
        --container-type singularity \
        --subject sub01 \
        --bids-dir /data/bids \
        --output-dir /data/derivatives/fmriprep
```

### Web UI on a cluster

```bash
# Start on a compute node
singularity exec --writable-tmpfs -B /data:/data \
    fmriflow.sif fmriflow serve --host 0.0.0.0 --port 8421

# From your laptop, SSH tunnel
ssh -L 8421:<compute-node>:8421 user@cluster

# Open http://localhost:8421
```

See `docker/examples/slurm_serve.sh` for a ready-to-use SLURM script.

### pycortex on HPC

pycortex writes to `~/.config/pycortex/` by default. On clusters with small home directory quotas, redirect it:

```bash
export OSTEX_FILESTORE=$SCRATCH/pycortex_store
singularity exec --writable-tmpfs -B $SCRATCH:$SCRATCH \
    fmriflow.sif fmriflow run /data/experiments/config.yaml
```

---

## SLURM Examples

Ready-to-use scripts are in `docker/examples/`:

| Script | Purpose |
|--------|---------|
| `slurm_single.sh` | Run one config: `sbatch slurm_single.sh config.yaml` |
| `slurm_array.sh` | Array job for multiple subjects: `sbatch slurm_array.sh config.yaml` |
| `slurm_serve.sh` | Run the web UI on a compute node |
| `slurm_preproc.sh` | Run fmriprep preprocessing for one subject |

---

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `FS_LICENSE` | — | Path to FreeSurfer license file |
| `FMRIFLOW_PLUGINS_DIR` | `~/.denizens/plugins` | User plugin directory |
| `FMRIFLOW_HEURISTICS_DIR` | `~/.denizens/heuristics` | Heuristic files for DICOM conversion |
| `FMRIFLOW_SUBJECTS_DB` | — | Path to subject metadata JSON |
| `FMRIFLOW_DATA_DIR` | `.` | Base for relative data paths |
| `MPLCONFIGDIR` | — | Matplotlib config (set to `/tmp/matplotlib` in containers) |
| `XDG_CACHE_HOME` | — | Cache directory (set to `/tmp/cache` in containers) |

---

## CI/CD

GitHub Actions builds and pushes images automatically:

- **On push to `main`:** builds both `runtime` and `full` images, pushes to GHCR
- **On version tags (`v*`):** same, with semver tags (e.g. `ghcr.io/osherifo/fmriflow:2.0.0`)
- **On PRs:** builds and runs tests, but does not push

Cluster users can always pull the latest:

```bash
singularity build fmriflow.sif docker://ghcr.io/osherifo/fmriflow:latest
```
