# Running fMRIflow with Docker

fMRIflow ships two Docker images so you don't have to install
fmriprep, FreeSurfer, heudiconv, and the Vite frontend toolchain by
hand.

| Variant | Size | Use when |
|---|---|---|
| **slim** | ~3–4 GB | You already have Docker (or apptainer) on the host and want fmriflow to delegate fmriprep to it. |
| **full** | ~25 GB | You want a single self-contained image — fmriprep + FreeSurfer + ANTs + AFNI baked in. |

Both images expose the web UI on port `8421` and run as a non-root
user. Persistent state lives under `$FMRIFLOW_HOME` on the host and
is bind-mounted into the container, so it survives container
restarts and image rebuilds.

## Working directory: `$FMRIFLOW_HOME`

fmriflow reads and writes everything from one host directory:

```
$FMRIFLOW_HOME/        # default ~/projects/fmriflow
├── addons/            # your heuristics, workflows, custom modules
├── configs/           # convert / preproc / autoflatten / workflow YAMLs
├── runs/              # run registry — needed for reattach
├── stores/            # structural-QC + post-preproc state
├── secrets/           # FreeSurfer license, etc.
├── subjects.json      # your subject metadata
└── data/              # MRI: bids/, dicoms/, derivatives/, work/, results/
```

The compose files bind `$FMRIFLOW_HOME` to `/workspace` inside the
container. See the [working-dir guide](working-dir.md) for the
full layout and tier model.

## Quickstart — slim image

```bash
git clone https://github.com/osherifo/denizenspipeline.git
cd denizenspipeline

# 1. (Optional) point fmriflow at a custom working dir.
export FMRIFLOW_HOME=~/projects/fmriflow

# 2. Bring it up.
docker compose up --build
```

On first boot the container runs `fmriflow init` to materialise the
empty layout under `$FMRIFLOW_HOME`. Drop your FreeSurfer license at
`$FMRIFLOW_HOME/secrets/freesurfer-license.txt`, or set
`FS_LICENSE_TEXT` in your shell to pass it inline.

Open `http://localhost:8421`.

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

## Splitting `data/` onto a separate disk

Set `$FMRIFLOW_DATA` on the host to a different path (e.g. a RAID
mount) and uncomment the matching `FMRIFLOW_DATA` env + volume in
`docker-compose.yml`:

```yaml
environment:
  FMRIFLOW_DATA: /data
volumes:
  - ${FMRIFLOW_DATA:-~/projects/fmriflow-data}:/data
```

Inside the container, BIDS / derivatives / work / results live
under `$FMRIFLOW_DATA` instead of `$FMRIFLOW_HOME/data/`.

## Mounted paths

| Host path | Container path | Purpose |
|---|---|---|
| `$FMRIFLOW_HOME` (default `~/projects/fmriflow`) | `/workspace` | Configs, addons, runs, stores, secrets, data subtree |
| `$FMRIFLOW_DATA` *(optional)* | `/data` | Big-data subtree (BIDS / derivatives / work / results) on a separate disk |
| `/var/run/docker.sock` *(slim only)* | same | docker-out-of-docker for fmriprep |

## File ownership on bind mounts

Bind-mounted directories pick up the uid/gid of the in-container
`fmriflow` user. By default that's `1000:1000`; align it with your
host user with:

```bash
PUID=$(id -u) PGID=$(id -g) docker compose up
```

## Passing the FreeSurfer license inline

If you don't want to drop a license file at
`$FMRIFLOW_HOME/secrets/freesurfer-license.txt`, set
`FS_LICENSE_TEXT` on your host (e.g. via `.env`):

```env
FS_LICENSE_TEXT="abc123\nyou@example.com\n0001\n..."
```

The entrypoint writes it to `$FMRIFLOW_HOME/secrets/freesurfer-license.txt`
on first boot.

## Troubleshooting

- **fmriprep sibling container can't see /workspace** — when slim
  spawns fmriprep via the docker socket, the *host* path is what
  the sibling container sees. Make sure your `$FMRIFLOW_HOME` lives
  at the same path on the host and inside the fmriflow container,
  or switch to the full image where everything runs in one container.
- **Heudiconv complains about `dcm2niix`** — both slim and full
  ship `dcm2niix` on PATH; if you've forked the Dockerfile and
  removed it, reinstall.
- **First boot looks empty** — that's expected. The entrypoint
  runs `fmriflow init` against the bind mount. Drop your saved
  configs, addons, and data into the corresponding subdirs and
  reload the UI.
