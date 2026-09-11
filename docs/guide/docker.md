# Running fMRIflow with Docker

fMRIflow ships two Docker images so you don't have to install
fmriprep, FreeSurfer, heudiconv, and the Vite frontend toolchain by
hand.

| Variant | Size | Use when |
|---|---|---|
| **slim** | ~4 GB | DICOM conversion, analysis and the web UI only — it has no fmriprep, so **preprocessing pipelines cannot run on it** at present. |
| **full** | ~11 GB | Everything, including preprocessing: fmriprep + FreeSurfer + ANTs baked in. **This is the supported image for preprocessing.** |

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
├── stores/            # structural-QC state
├── secrets/           # FreeSurfer license, etc.
├── subjects.json      # your subject metadata
└── data/              # MRI: bids/, dicoms/, derivatives/, work/, results/
```

The compose files bind `$FMRIFLOW_HOME` to `/workspace` inside the
container. See the [working-dir guide](working-dir.md) for the
full layout and tier model.

## Quickstart — guided setup

The easiest path is the interactive setup script:

```bash
./scripts/fmriflow-setup.sh          # full image
./scripts/fmriflow-setup.sh --slim   # slim image (orchestrator only)
```

It asks where `$FMRIFLOW_HOME` should live (creating it if needed), saves
the choice to `.env` so later plain `docker compose` invocations reuse it,
checks for symlinks that would dangle inside the container, builds the
image, and runs in the foreground (Ctrl-C stops it).

For day-to-day use there are three small scripts, all accepting `--slim`
to target the slim image instead of the full one:

```bash
./scripts/fmriflow-up.sh              # start detached, wait for the server, print the URL
./scripts/fmriflow-up.sh --build      # rebuild the image, then start
./scripts/fmriflow-down.sh            # stop (add --logs to print the last log lines first)
./scripts/fmriflow-build.sh           # build the image only, without starting it
./scripts/fmriflow-build.sh --no-cache   # rebuild every layer; --pull refreshes the base image
```

`fmriflow-build.sh` warns when `frontend/src` has uncommitted changes
(the image ships whatever SPA bundle is in the repo, so run
`npm run build` first), and when a running container is still on the
previous image. `fmriflow-down.sh`
removes the container but keeps the image and everything under
`$FMRIFLOW_HOME`.

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

Preprocessing is **not available** on the slim image: the fmriprep node
runs fmriprep from PATH, and slim does not ship it. Launching fmriprep in
a sibling container through the host's Docker socket is not supported at
present (the socket mount is kept in `docker-compose.yml` for a future
iteration). Use the full image for anything under Preprocessing.

## Standalone — full image

The full image is built **on top of** `nipreps/fmriprep`, so
fmriprep, FreeSurfer and ANTs are on PATH, with dcm2niix added on top.
The fmriprep node runs fmriprep straight from PATH here; there is nothing
to configure:

```bash
docker compose -f docker-compose.full.yml up --build
```

Pin a specific fmriprep version with:

```bash
docker compose -f docker-compose.full.yml build \
    --build-arg FMRIPREP_TAG=24.1.1
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
| `/var/run/docker.sock` *(slim only)* | same | reserved for a future docker-out-of-docker fmriprep; unused today |

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

## Pycortex subjects

Flatmap reporters and pycortex transforms read subjects from the pycortex
*filestore*. The container points pycortex at `$FMRIFLOW_HOME/pycortex/`
(`/workspace/pycortex` inside the container) on every start, so imported subjects and
transforms live in your working directory and survive rebuilds. Put existing pycortex
subject folders there, or import new ones with Autoflatten.

To use another location, set `PYCORTEX_FILESTORE` in the compose `environment:` block
to a path visible inside the container (for example a bind-mounted store). The
**Settings** page shows the store pycortex is using and the subjects in it.

## Browsing other locations

Path fields in the UI can **Browse…** the server's filesystem, but only under the data
roots (`$FMRIFLOW_DATA`, `$FMRIFLOW_HOME`). Inside Docker that is the container's view,
so a share mounted on the host is invisible until it is bound into the container. Add a
**read-only** bind mount and list it in `FMRIFLOW_BROWSE_ROOTS`:

```yaml
services:
  fmriflow:
    volumes:
      - ${FMRIFLOW_HOME}:/workspace
      - /path/to/lab/share:/shares/lab:ro          # read-only: the app can read, never write
    environment:
      FMRIFLOW_BROWSE_ROOTS: /shares/lab             # colon-separated for several
```

Paths picked there are container paths (`/shares/lab/...`), which is what every stage
needs. A typed host path that the container cannot see gets a warning under the field.

## Troubleshooting

- **A preprocessing run fails with "fmriprep is not on PATH"** — you are
  on the slim image. Preprocessing needs the full image.
- **Heudiconv complains about `dcm2niix`** — both slim and full
  ship `dcm2niix` on PATH; if you've forked the Dockerfile and
  removed it, reinstall.
- **First boot looks empty** — that's expected. The entrypoint
  runs `fmriflow init` against the bind mount. Drop your saved
  configs, addons, and data into the corresponding subdirs and
  reload the UI.
