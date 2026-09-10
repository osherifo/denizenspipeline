# Preprocessing

fMRIflow preprocessing is **one graph**: a pipeline is a set of nodes — fmriprep, a
BIDS-App, a shell command, a smoothing step, a hand-written nipype workflow you imported —
wired port to port and run as a single nipype workflow. The same page builds it, runs it,
watches it, and checks its outputs. Everything ends in a `PreprocManifest`, the JSON
contract the analysis stage reads.

Open **Preprocessing** in the sidebar. Four tabs:

| Tab | What it does |
|---|---|
| **Build** | Pick a template or a saved pipeline, edit it in the graph editor, set node parameters, bind a subject and paths, run. |
| **Runs** | Every pipeline run: live node status on the graph, checkpoints, per-node outputs, the inner fmriprep DAG, the log, Resume / Restart. |
| **Library** | The node library: what each node needs, its parameters and source; author a new node; import an existing nipype pipeline. |
| **Outputs** | Manifests on disk; collect a manifest from derivatives produced elsewhere. |

## Environment setup

fMRIPrep has heavy dependencies, so install fMRIflow into the conda env that already has fmriprep:

```bash
# Option A: install the pipeline into your fmriprep env (recommended)
conda activate fmriprep-py310
cd fmriflow
pip install -e .

# Option B: install fmriprep into the pipeline env
conda activate fmriflow
pip install fmriprep
```

fmriprep runs **bare**, from PATH — the full Docker image ships it, and the
node's preflight reports when it is missing. Running fmriprep inside its own
docker or apptainer container is not supported at present.

You also need a FreeSurfer license file:

```bash
export FS_LICENSE=~/fmriprep-local/fs_license.txt
```

## Quick check

```bash
fmriflow preproc doctor        # preflight every node: tools, env vars, python deps
```

## Workflow 1: the easy path — fmriprep from a template

1. **Build → Templates → `fmriprep_full`** (or `fmriprep_anat_only`, `fmriprep_func_precomputed_anat`).
   The pipeline is a single `fmriprep` node.
2. Click the node. Parameters are grouped — **Mode** (full / anat_only / func_only /
   func_precomputed_anat), **Anatomical**, **Functional**,
   **Fieldmaps**, **Output** (spaces, CIFTI), **Denoising**, **Resources**.
3. In the **Run** panel enter the subject label, the BIDS root and an output directory,
   then **Run pipeline**. The Runs tab opens on the new run.

From the CLI the same thing is:

```bash
fmriflow preproc run fmriprep_anat_only --subject 01 \
  --bids-dir ./testing/my_study/bids --output-dir ./testing/my_study/derivatives \
  --param fmriprep.output_spaces='["T1w"]'
```

Save the pipeline under a name to reuse it (it lands in `$FMRIFLOW_HOME/configs/preproc/`).
The **Run** panel is saved with it, as `run_defaults` — subject, BIDS root, output and
work dirs, plugin, cache — so reopening a saved pipeline brings those back and a rerun
is one click. Templates carry no defaults. `fmriflow preproc run <saved-name>` uses the
saved values for any flag you leave out.

### When a run fails

The run header shows the **cause** — the innermost exception message, e.g.
`ValueError: fmriprep: mode 'func_precomputed_anat' requires fs_subjects_dir …` —
above a **Traceback** button with the full nipype error text, one button per
**crash file** nipype wrote (its node inputs and traceback), and the runner's
`stdout.log`, which opens by itself for failed and lost runs. Selecting the failed
node on the graph opens its work directory, where a container app's own output is
`stdout.log`. The same data is at `GET /api/preproc/runs/{id}` (`cause`, `errors`,
`crashes`), `…/crashes/{name}` and `…/log?tail=N`.

## Workflow 2: build a pipeline

The editor is the graph: click a node in the palette to add it, drag from an output
port to an input port to connect, Backspace deletes the selection. A plain chain such as
*fmriprep → smooth → regress confounds* is just a graph with one edge per node.

Every path you type in the Build tab has a **…** button next to it that opens the
server-side directory browser: the Run panel's `output_dir`, `bids_dir`,
`derivatives_dir` and `work_dir`, any node input port that names a directory or
file, and node parameters typed `dir`, `file` or `path` (fmriprep's
`fs_subjects_dir` and `fs_license_file`, for instance). The browser can create a
**New folder**, which is the usual way to make a fresh output directory. A typed
path the server cannot see gets a warning under the field; bindings such as
`$inputs.bids_dir` are left alone.

For each node the side panel shows:

- **Inputs** — each input port is either connected (an edge), bound to a pipeline input
  (`$inputs.bids_dir`), or given a literal value. **×N** on a port makes the node
  iterate over the list arriving there (one nipype `MapNode` per item — e.g. smooth
  every BOLD run).
- **Parameters** — a schema-driven form, grouped when the node declares groups.
- **Manifest role** — which node's outputs define the manifest (★), and which port
  the manifest's BOLD files should point at (`bold from`).

**Validate** checks ports, kinds, doubly fed inputs and cycles before you run.

The shipped templates are the three fmriprep ones. Anything else — smoothing or
confound regression on derivatives produced elsewhere (`derivatives_source` →
`smooth` → `regress_confounds`), or a hand-written nipype workflow such as the
`reference_fsl_ants` composite node — is built from the palette and saved as a
pipeline of your own.

### Your own templates

**Save as template** in the Build toolbar keeps the current graph as a starting point
of your own. It lands in `$FMRIFLOW_HOME/addons/pipelines/<name>.yaml` and shows up in
the Templates list with a `user` badge; the bundled ones are read-only, and a user
template cannot take a bundled name. Delete one with the ✕ on its card.

A template differs from a saved pipeline in two ways. Loading it always gives you an
unsaved draft, so **Save** never overwrites the template itself. And the Run panel is
not kept: a template should take its paths from pipeline inputs bound at run time, so
it works on the next dataset as well as this one. If a node parameter still holds a
literal path (`/data/...`), the save goes through but tells you which values will not
travel.

`fmriflow preproc run <template-name>` resolves user templates the same way it does
bundled ones.

### Reusing a FreeSurfer reconstruction

`func_precomputed_anat` reuses an existing FreeSurfer subject instead of running
recon-all. Point `fs_subjects_dir` at the subjects directory and, when the subject is not
named `sub-<label>` there (a pycortex-style `sub01fs`, say), set `fs_subject` to its name.
Two things happen that you should know about:

- The run refuses to start if the subject is missing or incomplete, listing the subjects
  it did find. Without this, fmriprep would silently run a full recon-all instead.
- fmriprep works on the reconstruction **in place** and "completes" it: an older
  FreeSurfer version gets the volumes, transforms and surface measures a current one
  writes, once, on first use. Point `fs_subjects_dir` at a copy you are happy to let it
  modernise, not at a lab master. With `fs_subject`, nothing in your directory is renamed:
  a small subjects dir under the run's work dir links `sub-<label>` to the subject.

## Workflow 3: watch a run

The Runs tab shows the pipeline graph with each node coloured by status (running /
done / cached ⟲ / failed) and a checkpoint badge. Click a node to see its **outputs**
inline (the nipype work dir: NIfTIs render inline, reports and JSON open in place, crash
files are shown). **Double-click a node, or press Open**, for the node popup — a window
with a tab per thing the node can show:

- every node: **Overview** (status, parameters, outputs by port), **Outputs**,
  **Checkpoints**, and **Log** when the app wrote its own stdout;
- an app node that declares the capability (fmriprep does): **Inner DAG** — its own
  nipype workflow (recon-all, BOLD preprocessing, field-map estimation) with lanes per
  run, friendly labels and docs links, live while it runs; **Summary** — spaces, runs
  with motion / tSNR badges, confounds; **Report** — the subject's HTML report; and
  **Structural QC** — FreeSurfer surfaces over the T1 with the review / sign-off form.

Everything in the popup is scoped to *this run's* node, not to whichever manifest
matches the subject. The Workflows view opens the same popup for a preprocessing
stage's backend node with **Backend node →**. Which tabs a node gets is decided by the
capabilities it derives from its contract or declares in a `UI` class attribute (see the
[pipeline reference](../reference/preproc-pipeline.md#node-contract)); a node you write
yourself gets the generic tabs without any frontend work.

**Checkpoints** are the filmstrip under the graph. As recon-all writes each file the
fmriprep node measures it — `orig/nu/T1.mgz` intensity statistics (unique values, modal
fraction), `wm.mgz` volume, `?h.white` Euler numbers, `?h.thickness` mean and
zero-thickness fraction, `aseg.stats` — and judges it against a norms table:
**ok**, **suspicious**, **bad** (with the reasons), or **unknown**. Once BOLD runs land it also
checks each one: NaN/Inf and dead volumes, RF-spike volumes, framewise displacement and
rigid-body extremes from the confounds, the estimated fieldmap's range and the GRE
fieldmap's ΔTE, the per-run reference volume, and the CompCor regressors. A bad `nu.mgz` is
visible ~20 minutes into a 10-hour run instead of after it. Every node also gets generic
output checks (file exists, non-empty, 4D where a BOLD is expected). Tick **abort on bad
checkpoint** in the Run panel to have a `bad` verdict terminate the run.

Both halves of a checkpoint are editable without touching Python. **Library →
Checkpoint norms** is the threshold table: change a bound, blank it to go back to the
built-in, Save — it lands in `configs/norms.yaml` in your fMRIflow home. A node's panel has
a **Checks** section: untick a built-in check to skip it, or **Add check** with an artifact
path, a metric from the registry (the all-purpose `nifti_stats` covers most files) and
bounds typed one per line (`n_trs > 100`). **Try** evaluates it against a finished run's
node right there, so you see the metrics and verdict before a ten-hour run tells you the
template was wrong. Checks save with the pipeline. See the
[reference](../reference/preproc-pipeline.md#events-and-checkpoints) for the YAML and
for writing your own metric.

Runs are detached processes; a server restart cannot kill them. A run whose process is
gone shows as **lost**, and **Resume / Restart…** asks what you want: *Resume* launches
the same job and nipype skips every node whose inputs are unchanged; *Restart* ignores
the cache. Nothing resumes silently. **Rerun from** in the Run panel re-executes from a
named node onwards after you change a parameter downstream.

## Workflow 4: your own nodes and pipelines

**Library → New node** opens a Monaco editor with a scaffold for each kind:

- **node** (`interface`) — a class with `INPUTS` / `OUTPUTS` / `PARAM_SCHEMA` and a
  plain `run(inputs, out_dir, params)` returning output paths. No nipype knowledge
  needed; the adapter wraps it.
- **workflow** (`composite`) — `build(config)` returns a nipype `Workflow`; its
  `inputnode` / `outputnode` fields are the ports.
- **app** (`container_app`) — `build_command(...)` and `collect(...)` for a command-line
  tool run from PATH.

Files are saved to `$FMRIFLOW_HOME/addons/nodes/` and the library rescans. Addon files
written for the earlier registries (`@register_preproc_workflow`, `@register_transform`,
`@nipype_node`) still load — the decorators are aliases now.

**Library → Import nipype pipeline** takes a path to a `.py` that defines
`build(config)` (or `create_workflow` / `make_workflow`) returning a nipype `Workflow`, or
exposes a module-level `Workflow`. It becomes a composite node with the workflow's
`inputnode` / `outputnode` fields as ports, usable in any pipeline.

## Workflow 5: register outputs produced elsewhere

If fmriprep (or anything else) already ran, build the manifest without re-running:

```bash
fmriflow preproc collect \
  --backend fmriprep \
  --output-dir /data/derivatives/fmriprep/ \
  --subject sub01 \
  --task reading \
  --run-map '{"run-01": "story01", "run-02": "story02"}'

fmriflow preproc info     /data/derivatives/fmriprep/sub-sub01/preproc_manifest.json
fmriflow preproc validate /data/derivatives/fmriprep/sub-sub01/preproc_manifest.json
```

The same lives under **Outputs → Collect**. Then point an analysis config at it:

```yaml
response:
  loader: preproc
  manifest: /data/derivatives/fmriprep/sub-sub01/preproc_manifest.json
  mask_type: thick
```

## Confound regression

Either put a `regress_confounds` node in the pipeline (it takes the confounds TSV on its
`confounds_file` port and regresses the chosen columns out per voxel), or apply
regression when the analysis pipeline loads the data:

```yaml
response:
  loader: preproc
  manifest: manifest.json
  confounds:
    strategy: motion_24    # or: motion_6, acompcor, custom
    high_pass: 0.01
    fd_threshold: 0.5      # scrub high-motion TRs
```

## Migrating from the earlier surfaces

Stack presets, saved post-preproc graphs and `backend:`-style stage configs are converted
in one go:

```bash
fmriflow preproc migrate --dry-run     # report
fmriflow preproc migrate               # write pipelines, keep originals as *.migrated
```

Workflow YAMLs whose `preproc` stage still uses `backend:` / `backend_params:` are refused
with the same hint; pass `--workflows-dir` to convert those too.

## The manifest

`preproc_manifest.json` records everything about preprocessing: which node produced it,
its version and parameters, output space, per-run QC metrics (framewise displacement,
tSNR), file paths, and one `StepRecord` per node that ran (parameters, work dir, duration,
nipype hash). The analysis pipeline validates this before loading data, catching
mismatches early.

See the [pipeline reference](../reference/preproc-pipeline.md) for the YAML schema, the
run request, the node contract, the event and checkpoint records, and the HTTP API.
