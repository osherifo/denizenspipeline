# Docker images for fmriflow

| Variant | Dockerfile | Size | What's included |
|---|---|---|---|
| **slim** | `Dockerfile.slim` | ~4 GB | FastAPI backend + Vite frontend + heudiconv + bids-validator + dcm2niix + the Docker CLI. fmriprep is delegated to the host (docker socket, or apptainer-on-host). |
| **full** | `Dockerfile.full` | ~11 GB | slim's fmriflow layer on top of `nipreps/fmriprep` (fmriprep, FreeSurfer, ANTs). No second runtime needed; preproc YAMLs can use `container_type: bare`. |

```bash
docker compose up --build                              # slim
docker compose -f docker-compose.full.yml up --build   # full
```

The UI comes up on <http://localhost:8421>.

**Full usage documentation lives in [`docs/guide/docker.md`](../docs/guide/docker.md)** —
working-dir layout, the `$FMRIFLOW_HOME` / `$FMRIFLOW_DATA` split, FreeSurfer licensing,
apptainer-on-host, file ownership, and troubleshooting. That guide is the single source of
truth; this file only describes the two build targets so the two can't drift apart again.

## Notes for people editing these images

- **`entrypoint.sh` is shared by both images.** It writes the FreeSurfer license from
  `FS_LICENSE_TEXT` when set, aligns the `fmriflow` user with `PUID`/`PGID`, joins the
  mounted docker socket's group, runs `fmriflow init`, then drops privileges via `gosu`.
- **The Docker CLI is installed from the official static tarball**, pinned by the
  `DOCKER_CLI_VERSION` build arg. Debian's `docker.io` package ships only the daemon
  (`dockerd`, `docker-proxy`, `docker-init`) and *not* `/usr/bin/docker`, which silently
  broke docker-out-of-docker — `shutil.which("docker")` returned `None` and the fmriprep
  backend reported itself unavailable.
- **The socket group is resolved at run time, not build time.** The gid owning
  `/var/run/docker.sock` differs per host, so the entrypoint reads it with `stat` and adds
  `fmriflow` to a matching group. Baking a gid into the image does not port between machines.
- **`chown -R` over `$FMRIFLOW_HOME` only runs when ownership is actually wrong.** That
  directory holds the data subtree and can be hundreds of GB. Set `FMRIFLOW_FORCE_CHOWN=1`
  to force a full recursive pass.
- **`.dockerignore` deliberately excludes `fmriflow/server/static`** — the frontend is
  rebuilt from source in stage 1 and copied in before `pip install`, so hatch packages it
  into the wheel. Do not add it to `force-include` in `pyproject.toml`; it is already inside
  the packaged tree and a second entry makes the wheel build fail outright.
