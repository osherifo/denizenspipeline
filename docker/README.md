# Docker images for fmriflow

Two variants live here:

| Variant | Dockerfile | Size | What's included |
|---|---|---|---|
| **slim** | `Dockerfile.slim` | ~1–2 GB | FastAPI backend + Vite frontend + heudiconv + bids-validator + dcm2niix. fmriprep is delegated to the host (docker socket, or apptainer-on-host). |
| **full** | `Dockerfile.full` | ~25 GB | slim + everything in `nipreps/fmriprep` (fmriprep, FreeSurfer, ANTs, AFNI). No second runtime needed; preproc YAML can use `container_type: bare`. |

## Quickstart (slim)

From the repo root:

```bash
mkdir -p license experiments results derivatives bids dicoms
cp /path/to/your/freesurfer_license.txt license/license.txt

docker compose up --build
# UI on http://localhost:8421
```

Configure your preproc YAML with:

```yaml
backend: fmriprep
container_type: docker
container: nipreps/fmriprep:24.1.1
```

## Standalone (full)

```bash
docker compose -f docker-compose.full.yml up --build
```

Then in your preproc YAML:

```yaml
backend: fmriprep
container_type: bare
```

The full image first build is slow because it pulls `nipreps/fmriprep`.

## Apptainer-on-host instead of docker socket

If your host runs apptainer/singularity (e.g. shared HPC node), edit
`docker-compose.yml`: comment the `/var/run/docker.sock` line, then add

```yaml
    volumes:
      - /usr/bin/apptainer:/usr/bin/apptainer:ro
      - /path/to/your/fmriprep.sif:/opt/fmriprep.sif:ro
    environment:
      FMRIFLOW_SINGULARITY_BIN: /usr/bin/apptainer
```

In your preproc YAML:

```yaml
backend: fmriprep
container_type: apptainer
container: /opt/fmriprep.sif
```

## What's mounted where

| Host path | Container path | Purpose |
|---|---|---|
| `fmriflow-state` (named volume) | `/data` | `~/.fmriflow/` — run registry, modules, QC store, workflows, registered heuristics |
| `./experiments/` | `/workspace/experiments` | YAML configs (convert, preproc, autoflatten, workflows) |
| `./derivatives/` | `/workspace/derivatives` | fmriprep + autoflatten outputs |
| `./results/` | `/workspace/results` | analysis run outputs |
| `./bids/` (ro) | `/workspace/bids` | BIDS roots |
| `./dicoms/` (ro) | `/workspace/dicoms` | DICOM roots |
| `./license/` (ro) | `/data/license` | FreeSurfer license file |
| `/var/run/docker.sock` (slim only) | same | Lets fmriflow spawn sibling fmriprep containers |

## File ownership on bind mounts

The container creates files as `fmriflow:fmriflow`, with uid/gid taken
from `PUID`/`PGID` (default `1000:1000`). Override per-host with:

```bash
UID=$(id -u) GID=$(id -g) docker compose up
```

## Pinning fmriprep version (full image)

```bash
docker compose -f docker-compose.full.yml build \
    --build-arg FMRIPREP_TAG=24.1.1
```

## Troubleshooting

- **`heudiconv: command not found`** — slim image only ships heudiconv on PATH; if you derived your own image, re-run `pip install heudiconv`.
- **fmriprep container can't see /workspace** — when running fmriprep as a sibling container via the docker socket, the *host* path is what the sibling sees. Make sure your bind mounts match between fmriflow and the spawned fmriprep container, or use the full image instead.
- **FreeSurfer license errors** — confirm `license/license.txt` exists and is readable, or set `FS_LICENSE_TEXT` in your shell env.
