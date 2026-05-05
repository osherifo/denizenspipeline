# Structural QC Review

After fmriprep finishes the structural side of preprocessing (skull strip,
T1↔surface alignment, FreeSurfer segmentation), you usually want to *look
at it* before letting any functional analysis depend on it. fMRIflow has a
small reviewer surface for exactly that.

## Where to find it

Three entry points to the same panel:

- **Preprocessing → Preproc** → click a subject's manifest → scroll to
  the **Structural QC** section under the Runs table.
- **Workflows → Workflow run detail.** Once the preproc stage finishes
  (`status: done`), the Preproc block in the workflow graph gains a
  **Structural QC →** button — clicking it opens the panel as a modal
  for the subject that just preprocessed.
- **Preprocessing → QC Reviews** → click a row to reopen the panel
  for any subject that already has a saved review.

## What you can do

### Inspect the images

- **Show fmriprep report** — toggles the fmriprep HTML report inline
  (skull-strip overlay, T1↔surface alignment, segmentation slices,
  motion summaries). This alone is enough to decide on routine subjects.
- **Show 3D viewer** — opens an embedded
  [niivue](https://github.com/niivue/niivue) canvas with `mri/T1.mgz`
  plus FreeSurfer surfaces. Drag to rotate; scroll to zoom. The viewer
  has a toolbar with:
    - **View**: *Multi* (default — multi-planar slice view), *Axial*,
      *Coronal*, *Sagittal*, *3D* render.
    - **Volume on / off**: hide the T1 in 3D so the cortex meshes are
      unobstructed.
    - **Surfaces** (multi-toggle): *pial* (green), *white* (red),
      *inflated* (blue) — colour-coded to match freeview's defaults
      (pial=green, white=red). Toggle any combination on at once;
      *clear* hides them all.
    - **X-ray** slider (0..1): drives niivue's global mesh-transparency
      pass. Lower values = outer mesh wins (opaque); higher values =
      inner mesh shows through. Useful when both pial and white are on
      and you want to see one through the other in 3D.
    - **⤢ Fullscreen**: pop the canvas out to a `position: fixed`
      overlay. Niivue stays mounted across the toggle, so the volume
      isn't re-downloaded.
- **Copy freeview command** *(only when status = Needs edits)* — for
  the cases the in-browser viewer can't handle (segmentation editing
  etc.), copies a ready-made `freeview` invocation to your clipboard,
  pre-loading T1, the brainmask, aseg, and pial/white surfaces. Files
  that don't exist on disk are silently skipped.

### Approve / reject the run

- **Pick a status** — *Pending* (the default for a never-reviewed
  subject), *Approve*, *Needs edits*, or *Rejected*. The chosen status
  is reflected by the coloured dot in the section header.
- **Reviewer + notes** — free text, saved alongside the status.
  Anything you type sticks with the YAML on disk so a future reviewer
  can pick up where you left off.
- **Save review** — writes the (status, reviewer, notes, timestamp,
  freeview-command-used) tuple to disk. Both the **Preprocessing →
  Preproc** sidebar pill and the **QC Reviews** view pick up the
  change on next reload.

The intended workflow:

1. Inspect the subject in the browser.
2. If something is wrong, mark **Needs edits** and click **Copy freeview
   command**.
3. Paste it into a terminal, fix the surfaces in freeview, then re-run
   `recon-all -autorecon2`.
4. Come back and flip the status to **Approve**.

## Reviewing across many subjects

Two surfaces help you find and act on saved reviews:

- **Status pill in the Preproc manifest list.** Sidebar →
  **Preprocessing → Preproc**. Each manifest row shows a small
  pill on the right reflecting the saved review status
  (*pending / approved / needs edits / rejected*).
- **QC Reviews view.** Sidebar → **Preprocessing → QC Reviews**.
  Lists every saved review across every dataset (newest first).
  Filter chips at the top — *All / Pending / Approved / Needs
  edits / Rejected* — show live counts. Clicking a row opens the
  same Structural QC panel for that subject in a modal; closing
  the modal reloads the list so any edits show up immediately.

The view also surfaces the underlying YAMLs you'd otherwise have to
grep on disk: dataset, reviewer, last-saved timestamp, notes, and a
truncated notes preview (hover to see the full text).

## Where reviews are stored

Each review is one YAML file at:

    ~/.fmriflow/structural_qc/<dataset>/<subject>.yaml

The format is stable and easy to grep — you can list all approved subjects
in a dataset with a simple shell loop, or check it into a separate repo if
you want a review log.

## API

For scripts and CI:

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/api/structural-qc/reviews` | list all reviews across all datasets (optional `?dataset=` filter) |
| `GET`  | `/api/preproc/subjects/{subject}/structural-qc` | current review (or default *pending*) |
| `POST` | `/api/preproc/subjects/{subject}/structural-qc` | save a review |
| `GET`  | `/api/preproc/subjects/{subject}/structural-qc/freeview-command` | freeview command for the subject |
| `GET`  | `/api/preproc/subjects/{subject}/structural-qc/report` | fmriprep HTML report |
| `GET`  | `/api/preproc/subjects/{subject}/structural-qc/fs-file?rel=mri/T1.mgz` | a single FreeSurfer file (whitelisted suffixes only) |

The FS-file endpoint is what powers the niivue viewer; it refuses paths
that escape the FreeSurfer subject directory and only serves a small set
of suffixes (`.mgz`, `.pial`, `.white`, `.inflated`, `.nii.gz`, etc.).
