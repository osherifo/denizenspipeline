# Running fMRIflow with Docker

fMRIflow ships two Docker images so you don't have to install
fmriprep, FreeSurfer, heudiconv, and the Vite frontend toolchain by
hand.

| Variant | Size | Use when |
|---|---|---|
| **slim** | ~1–2 GB | You already have Docker (or apptainer) on the host and want fmriflow to delegate fmriprep to it. |
| **full** | ~25 GB | You want a single self-contained image — fmriprep + FreeSurfer + ANTs + AFNI baked in. |

Both images expose the web UI on port `8421` and run as a non-root
user. Persistent state (run registry, modules, QC store, workflow
configs) lives on a named Docker volume so it survives container
restarts.

## Quickstart — slim image

The slim image runs fmriflow as the orchestrator and shells out to
the host's Docker daemon to spawn fmriprep as a sibling container.
This is the recommended path on a workstation that already runs
Docker.

```bash
git clone https://github.com/osherifo/denizenspipeline.git
cd denizenspipeline

# 1. Drop your FreeSurfer license under ./license/.
mkdir -p license experiments results derivatives bids dicoms
cp /path/to/your/freesurfer_license.txt license/license.txt

# 2. Bring it up.
docker compose up --build
```

Open `http://localhost:8421` and you should see the fmriflow UI.

In your preproc YAML, point fmriprep at the bidsapp image:

```yaml
backend: fmriprep
container_type: docker
container: nipreps/fmriprep:24.1.1
```

## Standalone — full image

The full image is built **on top of** `nipreps/fmriprep`, so
fmriprep, FreeSurfer, ANTs, AFNI, and dcm2niix are all on PATH.
Preproc YAMLs can use `container_type: bare` directly:

```bash
docker compose -f docker-compose.full.yml up --build
```

```yaml
backend: fmriprep
container_type: bare
```

Pin a specific fmriprep version with:

```bash
docker compose -f docker-compose.full.yml build \
    --build-arg FMRIPREP_TAG=24.1.1
```

## Apptainer-on-host (HPC pattern)

On nodes that run apptainer/singularity instead of Docker, you can
keep using the slim image and bind the apptainer binary in:

1. Edit `docker-compose.yml` and **comment out** the line
   `- /var/run/docker.sock:/var/run/docker.sock`.
2. Add to the `volumes:` block:
   ```yaml
       - /usr/bin/apptainer:/usr/bin/apptainer:ro
       - /path/to/your/fmriprep.sif:/opt/fmriprep.sif:ro
   ```
3. Add to the `environment:` block:
   ```yaml
       FMRIFLOW_SINGULARITY_BIN: /usr/bin/apptainer
   ```
4. In your preproc YAML:
   ```yaml
   backend: fmriprep
   container_type: apptainer
   container: /opt/fmriprep.sif
   ```

## Mounted paths

| Host path | Container path | Purpose |
|---|---|---|
| `fmriflow-state` (named volume) | `/data` | `~/.fmriflow/` — run registry, modules, QC store, workflows, registered heuristics |
| `./experiments/` | `/workspace/experiments` | Convert / preproc / autoflatten / workflow YAML configs |
| `./derivatives/` | `/workspace/derivatives` | fmriprep + autoflatten outputs |
| `./results/` | `/workspace/results` | Analysis run outputs |
| `./bids/` (ro) | `/workspace/bids` | BIDS roots |
| `./dicoms/` (ro) | `/workspace/dicoms` | DICOM roots |
| `./license/` (ro) | `/data/license` | FreeSurfer license file |
| `/var/run/docker.sock` *(slim only)* | same | docker-out-of-docker for fmriprep |

Adjust the host paths in `docker-compose.yml` to match where your
data actually lives.

## File ownership on bind mounts

Bind-mounted directories pick up the uid/gid of the in-container
`fmriflow` user. By default that's `1000:1000`; align it with your
host user with:

```bash
UID=$(id -u) GID=$(id -g) docker compose up
```

This is sticky in the named volume, so set it once at first launch.

## Passing the FreeSurfer license inline

If you don't want to bind-mount a license file, set the env var
`FS_LICENSE_TEXT` on your host (e.g. via a `.env` file):

```env
FS_LICENSE_TEXT="abc123\nyou@example.com\n0001\n..."
```

The container's entrypoint writes it into `$FS_LICENSE` on first
boot, but that path must be writable. If your Compose setup
bind-mounts `./license` read-only at `/data/license` and sets
`FS_LICENSE` inside that mount, inline mode will not work as-is.
For `FS_LICENSE_TEXT`, remove that read-only license mount or point
`FS_LICENSE` at a writable location under `/data` instead.

## Troubleshooting

- **fmriprep sibling container can't see /workspace** — when slim
  spawns fmriprep via the docker socket, the *host* path is what
  the sibling container sees. Make sure your `./derivatives/` etc.
  sit at paths that exist on the host and inside the fmriflow
  container at the same location, or switch to the full image
  where everything runs in one container.
- **Heudiconv complains about `dcm2niix`** — both slim and full
  ship `dcm2niix` on PATH; if you've forked the Dockerfile and
  removed it, reinstall.
- **`mkdir: cannot create /data/.fmriflow`** — the named volume
  isn't writable by the in-container user. Re-run with
  `UID=$(id -u) GID=$(id -g) docker compose up` so the entrypoint
  picks up the right uid/gid.
