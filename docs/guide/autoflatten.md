# Autoflatten

Automated cortical surface flattening. Takes FreeSurfer reconall outputs and produces flat patches suitable for [pycortex](https://gallantlab.github.io/pycortex/) visualization.

## Why it exists

After fmriprep runs FreeSurfer reconall, you have white/pial/inflated surfaces but no flatmaps. Creating flatmaps is traditionally a manual process — open tksurfer/freeview, draw the medial wall cut, run `mris_flatten`, and import into pycortex — often the biggest bottleneck in setting up a new subject for surface-based analysis.

[autoflatten](https://github.com/gallantlab/autoflatten) automates this. fMRIflow wraps it and adds a UI, log streaming, a status checker, and pycortex import.

## What it does

1. **Project** cut templates from fsaverage to the subject's surface using `mri_label2label`
2. **Refine** the cuts with geodesic shortest paths
3. **Flatten** each hemisphere using a JAX-accelerated optimizer (or the FreeSurfer `mris_flatten` tool)
4. **Generate** preview PNGs of the flat patches
5. **Import** surfaces + flat patches into the pycortex database (optional)

## Installation

Autoflatten is an optional dependency:

```bash
pip install "fmriflow[flatten]"
```

For the full experience also install pycortex:

```bash
pip install "fmriflow[flatten,viz]"
```

## Prerequisites

- A FreeSurfer subject directory with reconall outputs (`surf/lh.inflated`, `surf/rh.inflated`, etc.)
- `FREESURFER_HOME` and `SUBJECTS_DIR` set — needed for the projection step
- FreeSurfer 7.0+ on PATH (for `mri_label2label`)
- pycortex, if you want automatic import

These are all satisfied after a successful fmriprep run with `mode: full` or `mode: anat_only`.

## Web UI

The Autoflatten view appears in the sidebar under the **Preprocessing** group, alongside DICOM → BIDS and Preproc. It has four tabs:

### Status tab

Check what's installed and inspect a subject's state. Enter the subjects directory and subject name, and you'll see:

| Indicator | Meaning |
|-----------|---------|
| Subject directory | whether `<subjects_dir>/<subject>/` exists |
| FreeSurfer surfaces | whether `lh.inflated` / `rh.inflated` are present |
| Flat patches | whether any of `*.autoflatten.flat.patch.3d`, `*.full.flat.patch.3d`, or `*.flat.patch.3d` exist |
| pycortex surface | whether the subject is registered in the pycortex database |

If flat patches exist, their previews render as thumbnails below the status readout. Click an image to zoom.

The tab also tells you the next action: flatten, import, or "all set".

### Configs tab

Browse YAML autoflatten configs discovered under `./experiments/autoflatten/`.
Each file must have a top-level `autoflatten:` section matching the
`AutoflattenConfig` fields (see CLI section below). Clicking a config
shows a summary grid (subject, subjects_dir, hemispheres, backend) and
the raw YAML with a **Run** button. The same live progress panel used
by the Run/Import tabs streams below.

Schema (minimal):

```yaml
autoflatten:
  subjects_dir: /data/derivatives/freesurfer
  subject: sub-AN
  hemispheres: both         # both | lh | rh
  backend: pyflatten        # pyflatten | freesurfer
  overwrite: false
  import_to_pycortex: true
  pycortex_surface_name: ANfs   # optional
```

### HTTP API

```bash
# List configs
curl http://localhost:8000/api/autoflatten/configs

# Get one
curl http://localhost:8000/api/autoflatten/configs/ANfs.yaml

# Kick off (body is optional — fields shallow-merge onto the YAML)
curl -X POST http://localhost:8000/api/autoflatten/configs/ANfs.yaml/run
```

### Run / Flatten tab

Run autoflatten on a subject.

| Field | Description |
|-------|-------------|
| Subjects Dir | Path to FreeSurfer subjects directory |
| Subject | Subject ID (as it appears in `<subjects_dir>/<subject>/`) |
| Backend | `pyflatten` (JAX, fast) or `freesurfer` (traditional `mris_flatten`) |
| Hemispheres | `both`, `lh`, or `rh` |
| Overwrite existing flat patches | By default, autoflatten skips if patches already exist |
| Import to pycortex | Register the subject + flatmap in the pycortex database after flattening |
| Surface name | pycortex subject name (defaults to `<subject>fs`) |

The progress panel below the form streams autoflatten's log output in real time. When it finishes, the flatmap preview PNGs appear below the summary.

### Import tab

If you already have flat patches from a previous autoflatten run or manual flattening, use this tab to import them into pycortex without re-flattening.

| Field | Description |
|-------|-------------|
| Subjects Dir | FreeSurfer subjects directory |
| Subject | Subject ID |
| LH Flat Patch | Path to existing `lh.*.flat.patch.3d` file |
| RH Flat Patch | Path to existing `rh.*.flat.patch.3d` file |
| Surface name | pycortex surface name override |

## CLI

### `fmriflow autoflatten run`

Flatten a subject. If patches already exist and `--overwrite` is not set, it skips flattening and just imports.

```bash
fmriflow autoflatten run \
    --subjects-dir /data/derivatives/freesurfer \
    --subject sub-sub01 \
    --backend pyflatten \
    --import-to-pycortex \
    --pycortex-surface sub01fs
```

### `fmriflow autoflatten import`

Import pre-computed flat patches into pycortex only.

```bash
fmriflow autoflatten import \
    --subjects-dir /data/derivatives/freesurfer \
    --subject sub-sub01 \
    --flat-patch-lh /path/to/lh.full.flat.patch.3d \
    --flat-patch-rh /path/to/rh.full.flat.patch.3d \
    --pycortex-surface sub01fs
```

### `fmriflow autoflatten status`

Show what exists for a subject (equivalent to the Status tab in the UI).

```bash
fmriflow autoflatten status \
    --subjects-dir /data/derivatives/freesurfer \
    --subject sub-sub01
```

### `fmriflow autoflatten doctor`

Check tool availability (autoflatten, pycortex, FreeSurfer).

```bash
fmriflow autoflatten doctor
```

## File naming

Autoflatten writes into the subject's `surf/` directory:

| File | Contents |
|------|----------|
| `{lh,rh}.autoflatten.flat.patch.3d` | The flat patch (binary FreeSurfer format) |
| `{lh,rh}.autoflatten.flat.patch.png` | Preview visualization |
| `{lh,rh}.autoflatten.flat.patch.3d.log` | Flattening log from autoflatten |

The `detect_existing_flats()` function also recognizes these alternate naming conventions for pre-existing patches:

- `{lh,rh}.full.flat.patch.3d` (manual flattening convention)
- `{lh,rh}.flat.patch.3d` (FreeSurfer default)

## Source field

Every autoflatten result records a `source` that answers "where did these patches come from?":

| source | Meaning |
|--------|---------|
| `autoflatten` | Freshly flattened by this run |
| `precomputed` | Patches already existed in the `surf/` dir, used as-is |
| `import_only` | User provided explicit `--flat-patch-lh/--flat-patch-rh`, no flattening |

## Non-Python dependencies

Autoflatten requires:

- **FreeSurfer** (for `mri_label2label`) — install system-wide
- **JAX** — installed automatically via `fmriflow[flatten]` on most platforms. For GPU support, install a matching `jax[cuda]` manually.

## Troubleshooting

**"pycortex not installed — skipping pycortex import"**
Install pycortex: `pip install "fmriflow[viz]"`. The flat patches are still produced on disk.

**"mri_label2label: command not found"**
FreeSurfer is not on PATH or `FREESURFER_HOME` is unset. Source FreeSurfer's setup script before starting the server.

**"ICA-AROMA requires MNI152NLin6Asym:res-2 in output_spaces"**
This is from fmriprep, unrelated to autoflatten — see the [preprocessing guide](preprocessing.md).

**Flat patches exist but previews don't appear in the UI**
Hit the Status tab's Check button again — it scans the `surf/` directory for `*.flat.patch.png` files and displays them. If the PNGs genuinely don't exist on disk, regenerate them by running autoflatten with `--overwrite`.
