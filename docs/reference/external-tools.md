# External tools

fMRIflow orchestrates programs it does not ship itself. This page is the
single list of what the pipeline calls by name, which stage needs it, and
which Docker image already has it. The Docker images are the supported
way to get a complete environment; nothing here needs to be installed by
hand when you run through `docker compose` (see the [Docker guide](../guide/docker.md)).

Versions are pinned in three places, and this page mirrors them:

| Pin | Where |
|---|---|
| fmriprep base image tag (also fixes FreeSurfer, ANTs, AFNI) | `docker/Dockerfile.full` (`FMRIPREP_TAG`) |
| Docker CLI in the slim image | `docker/Dockerfile.slim` (`DOCKER_CLI_VERSION`) |
| Python packages (nipype, heudiconv, pycortex, autoflatten, …) | `pyproject.toml` |

## Tool matrix

| Tool | Needed by | slim image | full image | Bare install |
|---|---|---|---|---|
| **heudiconv** (pip) | DICOM → BIDS conversion; also supplies `pydicom` for the Scan tab | ✓ | ✓ | `pip install heudiconv` |
| **dcm2niix** (apt) | heudiconv's converter backend | ✓ | ✓ | distro package or [rordenlab/dcm2niix](https://github.com/rordenlab/dcm2niix) |
| **bids-validator** (npm) | optional post-conversion validation; skipped when absent | ✓ | ✓ | `npm install -g bids-validator` (needs Node ≥ 18) |
| **nipype** (pip, required dependency) | every preprocessing pipeline — the execution engine | ✓ | ✓ | installed with `pip install fmriflow` |
| **fmriprep** | the `fmriprep` pipeline node (runs bare, from PATH) | ✗ — preprocessing needs the full image | ✓ 24.1.1 in-image | `pip install fmriprep` into the same env |
| **FreeSurfer** (`recon-all`, `mri_label2label`, …) + a license file | fmriprep node, structural QC, autoflatten | ✗ (inside the fmriprep container only) | ✓ 7.3.2 | FreeSurfer 7.x; point `FS_LICENSE` at `license.txt` |
| **ANTs** (`antsRegistration`) | fmriprep; the reference nipype template | ✗ | ✓ | ANTs ≥ 2.4 |
| **FSL** (`mcflirt`, `bet`, `flirt`; `FSLDIR`) | the reference nipype template only | ✗ | partial — the fmriprep base carries a trimmed FSL; run `fmriflow preproc doctor` to confirm | FSL 6.x |
| **AFNI** | fmriprep (ships in its base image) | ✗ | ✓ | only if running fmriprep bare |
| **docker** CLI or **apptainer** | not used by the pipeline at present (container-launched apps are a planned iteration) | docker CLI 27.3.1 present, unused | not needed | — |
| **autoflatten** + **pycortex** (pip extras `flatten`, `viz`) | Autoflatten tab, flatmap reporters | ✓ | ✓ | `pip install "fmriflow[flatten,viz]"` |
| **git** (and **git-lfs** for large artefacts) | Artifact Hub | git ✓, git-lfs ✗ | git ✓, git-lfs ✗ | distro packages |

## Checking an environment

Each stage has a `doctor` subcommand that resolves its binaries on
`PATH` and prints versions, so a missing tool is found before a
multi-hour run rather than after it:

```bash
fmriflow convert doctor       # heudiconv, dcm2niix, pydicom
fmriflow preproc doctor       # every node in the library: tools, env vars, python deps
fmriflow autoflatten doctor   # autoflatten, pycortex, FreeSurfer
```

The same checks are available over HTTP for the running server at
`GET /api/convert/tools` and `GET /api/autoflatten/doctor`. The
Docker build for the full image fails outright if any of `fmriprep`,
`recon-all`, `dcm2niix`, `heudiconv`, `autoflatten` or `bids-validator`
is not on `PATH`, so an image that built is an image with its tools.

## Preprocessing nodes declare their own needs

A pipeline node lists what it shells out to in `REQUIRED_TOOLS`,
`REQUIRED_ENV` and `REQUIRED_PYTHON`; the Library tab and `fmriflow
preproc doctor` preflight those declarations, and a run refuses to
start when a node's requirement is missing. When you write a node that
calls a new program, add it there rather than on this page — the
registry is the source of truth, this page is the summary. See the
[pipeline reference](preproc-pipeline.md) for the node contract.
