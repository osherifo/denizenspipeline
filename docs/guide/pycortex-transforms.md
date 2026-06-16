# Pycortex Transforms

Create the **functional → anatomy alignment** (a pycortex *transform*, or `xfm`) that lets the
analysis pipeline render your results on the cortical surface.

## Why it exists

[Autoflatten](autoflatten.md) imports a subject's surfaces into pycortex (the *anatomy* side), but
surface-based reporting also needs an **EPI → surface transform**: the mapping from a functional
(BOLD) grid to the subject's cortical surface. Reporters like [`flatmap`](../reference/modules.md#reporters) and the
`project_to_fsaverage` analyzer consume it via `cortex.Volume(scores, surface, transform)`.

This step mints that transform with a single, uniform name (default **`fmriflow`**) so every subject
uses the same transform name in configs — instead of a different ad-hoc name per subject.

## Prerequisites

- The subject's surfaces are already in pycortex (run [Autoflatten](autoflatten.md) first).
- A **functional reference volume** — a boldref, or the temporal mean of one run.
- For `automatic`: FreeSurfer on PATH (`bbregister`, `mri_coreg`) and the FreeSurfer subject
  discoverable under `$SUBJECTS_DIR` named like the pycortex subject.
- For `automatic_fsl`: FSL on PATH (`flirt`).

## CLI

```bash
# Boundary-based registration (FreeSurfer bbregister) — pycortex default
fmriflow pycortex-transform create ANfs /path/to/mean_bold.nii.gz --xfmname fmriflow --method automatic

# FSL FLIRT BBR variant (uses the pycortex surfaces; no $SUBJECTS_DIR name dependency)
fmriflow pycortex-transform create ANfs /path/to/mean_bold.nii.gz --method automatic_fsl

# Interactive manual aligner
fmriflow pycortex-transform create ANfs /path/to/mean_bold.nii.gz --method manual

# Inspect an existing transform's cortical-mask voxel count
fmriflow pycortex-transform status ANfs --xfmname fmriflow

# Check pycortex / FSL availability
fmriflow pycortex-transform doctor
```

The transform is stored in the **pycortex filestore** (never the FreeSurfer subject folder). To keep
a run isolated from a shared store, point pycortex at a scratch filestore via
`XDG_CONFIG_HOME` (a `pycortex/options.cfg` with a `filestore = ...` line).

### Methods

| Method | Engine | Notes |
|--------|--------|-------|
| `automatic` | FreeSurfer `bbregister` + `mri_coreg` | pycortex default; needs the FS subject under `$SUBJECTS_DIR` named like the pycortex subject |
| `automatic_fsl` | FSL FLIRT BBR | uses pycortex-stored surfaces; no `$SUBJECTS_DIR` naming requirement |
| `manual` | pycortex interactive aligner | blocking GUI; for hand alignment |

## Using the transform in analysis

Set the transform name in your subject config and render with the native-space flatmap reporter:

```yaml
subject_config:
  surface: ANfs
  transform: fmriflow

reporting:
  formats: [metrics, native_flatmap]
  native_flatmap:
    transform: fmriflow      # optional; defaults to subject_config.transform
    cmap: magma
    vmin: -0.01
    vmax: 0.1
```

The **`native_flatmap`** reporter wraps `result.scores` in `cortex.Volume(scores, surface, transform)`
and renders a quickflat PNG on the subject's own surface — the native-space counterpart to
`fsaverage_flatmap`.

!!! note "Mask voxel count must match the data"
    pycortex can only render a score array whose length equals
    `cortex.db.get_mask(surface, transform, "thick").sum()`. Keep the transform's reference grid and
    the response data in the **same space**. When responses are loaded straight from fmriprep BOLD via
    the [`preproc`](../reference/modules.md#response-loaders) response loader, they are masked by this same `(surface, transform)` mask, so the
    counts line up automatically.

## Where this fits

```
fmriprep  →  autoflatten (surfaces → pycortex)  →  pycortex-transform (this step)  →  analysis + flatmap
```
