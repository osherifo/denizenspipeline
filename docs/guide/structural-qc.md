# Structural QC Review

After fmriprep finishes the structural side of preprocessing (skull strip,
T1↔surface alignment, FreeSurfer segmentation), you usually want to *look
at it* before letting any functional analysis depend on it. fMRIflow has a
small reviewer surface for exactly that.

## Where to find it

Open the **Workflows** view, pick a subject's preproc manifest, and scroll
to the **Structural QC** section under the Runs table. The colored dot in
the section header reflects the current status.

## What you can do

- **Show fmriprep report** — toggles the fmriprep-generated HTML report
  inline. This is usually enough to decide on routine subjects.
- **Show 3D viewer** — opens an embedded [niivue](https://github.com/niivue/niivue)
  canvas with `mri/T1.mgz` plus the left/right pial surfaces overlaid.
  Drag to rotate; scroll to zoom.
- **Pick a status** — *Pending*, *Approve*, *Needs edits*, *Rejected*.
- **Reviewer + notes** — free text, saved alongside the status.
- **Copy freeview command** *(only when status = Needs edits)* — copies a
  ready-made `freeview` invocation to your clipboard, pre-loading T1, the
  brainmask, aseg, and pial/white surfaces. Files that don't exist on disk
  are silently skipped.

The intended workflow:

1. Inspect the subject in the browser.
2. If something is wrong, mark **Needs edits** and click **Copy freeview
   command**.
3. Paste it into a terminal, fix the surfaces in freeview, then re-run
   `recon-all -autorecon2`.
4. Come back and flip the status to **Approve**.

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
| `GET`  | `/api/preproc/subjects/{subject}/structural-qc` | current review (or default *pending*) |
| `POST` | `/api/preproc/subjects/{subject}/structural-qc` | save a review |
| `GET`  | `/api/preproc/subjects/{subject}/structural-qc/freeview-command` | freeview command for the subject |
| `GET`  | `/api/preproc/subjects/{subject}/structural-qc/report` | fmriprep HTML report |
| `GET`  | `/api/preproc/subjects/{subject}/structural-qc/fs-file?rel=mri/T1.mgz` | a single FreeSurfer file (whitelisted suffixes only) |

The FS-file endpoint is what powers the niivue viewer; it refuses paths
that escape the FreeSurfer subject directory and only serves a small set
of suffixes (`.mgz`, `.pial`, `.white`, `.inflated`, `.nii.gz`, etc.).
