# Preprocessing pipeline reference

A preprocessing pipeline is a graph of **nodes** run as one nipype workflow.
This page is the schema reference; the [Preprocessing guide](../guide/preprocessing.md)
explains how to use it.

## Pipeline YAML

Saved pipelines live in `$FMRIFLOW_HOME/configs/preproc/<name>.yaml`. The shape is
what the graph editor round-trips, so a file saved from the UI and one written by
hand look the same.

```yaml
schema_version: 1
name: fmriprep_smooth
description: fmriprep, then smooth every BOLD run.
inputs:                      # what a run must provide ($inputs.<name> in bindings)
  bids_dir: {kind: dir, description: BIDS root}
  subject:  {kind: str, description: participant label}
  output_dir: {kind: dir}
nodes:
  - id: fmriprep             # unique within the pipeline
    type: fmriprep           # a node-library name
    kind: container_app      # interface | container_app | composite | source
    data:
      params: {mode: full, output_spaces: [T1w]}
      bindings: {bids_dir: $inputs.bids_dir, subject: $inputs.subject, output_dir: $inputs.output_dir}
    position: {x: 0, y: 0}   # editor layout only
  - id: smooth
    type: smooth
    kind: interface
    data:
      params: {fwhm: 5.0}
      literal_inputs: {}     # fixed values for input ports
      iter: {handle: in_file}   # run once per item of the list arriving on in_file
edges:
  - {id: e1, source: fmriprep, sourceHandle: bold_preproc, target: smooth, targetHandle: in_file}
manifest:
  backend_node: fmriprep     # whose outputs define the PreprocManifest
  bold_from: smooth.out_file # re-point the manifest's BOLD files at this port
run_defaults:                # optional — the Run panel, saved with the pipeline
  subject: "01"
  bids_dir: /data/bids
  output_dir: /data/derivatives/my_study
  work_dir: /data/work/my_study
  plugin: Linear             # Linear | MultiProc (+ n_procs)
  use_cache: true
  abort_on_bad: false
  confounds_from: fmriprep.confounds
```

| Field | Meaning |
|---|---|
| `inputs` | Named values the run request supplies. Built-in names: `subject`, `bids_dir`, `derivatives_dir`, `output_dir`, `work_dir`, `dataset`, `task`, `sessions`; anything else comes from the request's `inputs` map. |
| `nodes[].data.params` | Node parameters (see the node's schema in the Library). Schema defaults apply when a key is absent. |
| `nodes[].data.bindings` | Input port → `$inputs.<name>`. |
| `nodes[].data.literal_inputs` | Input port → fixed value (a path, a string, a list). |
| `nodes[].data.iter` | `{handle: <port>}` or `{handles: [<port>, …]}` — the node becomes a nipype `MapNode` over the list(s) arriving on those ports. A handle's list comes from its edge, from a list in `literal_inputs` (what the Build tab writes when you type `0, 1, 2` into an iterated port), or from `values: [...]` (first handle). Several handles iterate in lockstep. Not available on composite nodes. |
| `edges[]` | `sourceHandle` is an output port of `source`, `targetHandle` an input port of `target`. An input port may be fed by exactly one of: an edge, a literal, a binding. |
| `manifest.backend_node` | The node whose collector builds the base `PreprocManifest` (fmriprep, a composite with `to_manifest`, or a source). |
| `manifest.bold_from` / `confounds_from` | `<node_id>.<port>`; the manifest's runs point at those files and `output_dir` becomes that node's work dir. |

`POST /api/preproc/pipelines/validate` (or the **Validate** button) reports every
structural problem: unknown node types or ports, kind mismatches, doubly fed ports,
undeclared inputs, cycles.

## Run request

Everything a run needs that is not part of the pipeline. Sent to
`POST /api/preproc/pipelines/run`, written to the run's `job.json`, and reused by
Resume / Restart.

| Field | Default | Meaning |
|---|---|---|
| `subject` | required | participant label |
| `output_dir` | required | derivatives root; the nipype work tree defaults to `<output_dir>/work` |
| `bids_dir`, `derivatives_dir`, `work_dir` | — | resolved by `$inputs.*` bindings |
| `dataset`, `task`, `sessions` | `unknown` | manifest labels |
| `inputs` | `{}` | extra named inputs |
| `plugin`, `n_procs` | `Linear` | nipype execution plugin |
| `use_cache` | `true` | `false` re-executes every node |
| `rerun_from` | `[]` | node ids to re-execute (their descendants follow) |
| `abort_on_bad` | `false` | terminate on a `bad` checkpoint verdict |
| `params_override` | `{}` | `{node_id: {param: value}}` |

**Caching.** nipype hashes every node's inputs (files by timestamp/size, parameters by
value); an unchanged node is skipped. The workflow name is `<pipeline>__sub_<subject>`,
so resuming a lost run or re-running after a parameter change reuses the work tree at
`<work_dir>/<workflow>/<node_id>/`. Container apps (fmriprep) also hash a content
fingerprint of their BIDS input, so edited raw data invalidates them.

## Workflow stage

A workflow YAML's `preproc` stage points at a config with a `preproc:` section:

```yaml
preproc:
  pipeline: fmriprep_anat_only     # a saved pipeline name, or an inline pipeline mapping
  subject: '01'
  output_dir: ./testing/my_study/derivatives
  bids_dir: ./testing/my_study/bids
  params_override: {fmriprep: {nthreads: 8}}
```

The old `backend:` / `backend_params:` shape is rejected with a pointer at
`fmriflow preproc migrate`.

## Node contract

A node is a class registered with `@preproc_node("<name>", kind=...)` in the built-in
package, a pip entry point (`fmriflow.preproc_nodes`), or a file under
`$FMRIFLOW_HOME/addons/nodes/`. Class attributes: `name`, `version`, `description`,
`INPUTS`, `OUTPUTS` (dicts of port specs `{kind, required, description}` or plain lists),
`PARAM_SCHEMA` (the same schema the module system uses, plus an optional `group` per
field), `REQUIRED_PYTHON`, `REQUIRED_TOOLS`, `REQUIRED_ENV`, `CONTAINER`, `CHECKS`, and an
optional `UI` dict (below).

| Kind | Implements | Notes |
|---|---|---|
| `interface` | `run(inputs, out_dir, params) -> outputs` | plain Python; wrapped into a nipype interface automatically |
| `source` | `run(...)` with no input ports | `bids_source`, `manifest_source`, `derivatives_source` |
| `container_app` | `validate(inputs, params)`, `build_command(inputs, params, out_dir)`, `collect(inputs, params, out_dir)`, optional `checkpoint_context(...)` | runs in its own process group; set `INNER_NIPYPE_LOG = True` to stream the app's inner nipype nodes |
| `composite` | `validate(config)`, `build(config) -> nipype.Workflow`, optional `to_manifest(config, outputs)` | ports are the fields of the workflow's `inputnode` / `outputnode` |

### Run views a node can offer (`ui`)

The run UI's node popup shows generic tabs for every node and one more per capability.
Capabilities are **derived** from the contract and can be overridden by a `UI` class
attribute; the node library serves them as `ui` on each node:

| key | derived from | unlocks |
|---|---|---|
| `inner_dag` | `INNER_NIPYPE_LOG = True` | **Inner DAG**: the app's own nipype workflow, live |
| `checkpoints` | a non-empty `CHECKS` | **Checkpoints** filmstrip |
| `log` | kind `container_app` (the app's `stdout.log`) | **Log** |
| `report` | the first output port of `kind: html` | **Report**: that HTML, with its relative assets |
| `structural_qc` | a `dir` port named `fs_subjects_dir` (or `role: freesurfer`) | **Structural QC**: FreeSurfer surfaces + review |
| `summary` | the `manifest` port (or `role: manifest`) | **Summary** of the manifest JSON |
| `label_map` | — (declare, e.g. `"fmriprep"`) | friendly names + docs links in the Inner DAG |
| `views` | — (declare) | opaque extra view ids; unknown ids are ignored |

```python
@preproc_node("my_app", kind="container_app")
class MyApp:
    INNER_NIPYPE_LOG = True
    OUTPUTS = {"report_html": {"kind": "html"}, "manifest": {"kind": "json"}}
    UI = {"label_map": None}          # everything else derives
```

The values are port names: the popup serves whatever path that port holds for *this
run's* node, via `GET /api/preproc/runs/{id}/nodes/{node_id}/…`. A node may adjust both
per run from its parameters with `ui_for_params(params)` and
`checks_for_params(params, checks)`: fmriprep hides Structural QC and skips the
FreeSurfer checks in its functional-only modes, and skips the functional checks in
`anat_only`.

The Library tab's **New node** offers a scaffold per kind; **Import nipype pipeline**
turns a `.py` file with a `build()` function or a module-level `Workflow` into a
composite node.

## Events and checkpoints

`<run dir>/events.jsonl` — one JSON object per line, streamed over `/ws/preproc/{run_id}`:

| `event` | Fields |
|---|---|
| `started` / `completed` / `failed` | `pipeline`, `run_id`, `workflow`, `n_nodes`, `duration_s`, `errors` |
| `node_start` / `node_done` / `node_fail` | `node` (dotted path), `workflow`, `leaf`, `t`, `cached`, `duration_s`; inner app nodes carry `inner: true` |
| `checkpoint` | `node`, `step`, `verdict`, `reasons`, `metrics` |

`<run dir>/checkpoints.jsonl` holds the full records
(`GET /api/preproc/runs/{id}/checkpoints`):

```json
{"stage": "preproc", "run_id": "pp_…", "node": "fmriprep_anat_only__sub_01.fmriprep",
 "step": "nu.mgz", "subject": "01",
 "metrics": {"n_unique": 70, "modal_fraction": 0.669, "modal_value": 110},
 "expectations": {"modal_fraction": ["<", 0.5], "n_unique": [">", 100]},
 "verdict": "bad", "reasons": ["modal_fraction=0.669 violates < 0.5"],
 "artifact": "…/sub-01/mri/nu.mgz", "t": 1757430000.0}
```

Verdicts: `ok` (all bounds hold), `bad` (a bound fails), `unknown` (a metric could not
be computed). A `sequence` parameter on the fmriprep node selects sequence-specific
overrides (`<step>@<sequence>` keys).

**Which checks are live.** The package defines many checks (FreeSurfer volumes and
surfaces, BOLD integrity, motion, fieldmaps, CompCor, physio), but only a short list is
switched on at the moment: `bold_output` (`is_4d`, `n_trs`) on every BOLD output port
and `sdc_delta_te` (`has_both_echoes`) on fmriprep's fieldmaps. The rest are defined but
neither evaluated nor listed, and a second, softer bound level ("suspicious") is parked
with them. The list is `ACTIVE_CHECKS` in `fmriflow/preproc/norms.py`; `None` switches
everything back on. Checks a pipeline declares itself (below) always run.

### Editing thresholds: `norms.yaml`

The built-in norms table (`fmriflow/preproc/norms.py`) is overlaid, metric by metric, by
`$FMRIFLOW_HOME/configs/norms.yaml`, which the **Library → Checkpoint norms** table edits
for you. A bound is `[op, value]`; `op` is one of `<`, `<=`, `>`, `>=`, `==`, `!=`,
`between` (value `[lo, hi]`). Only what you write changes; everything else stays built-in,
and the file is re-read on change.

```yaml
bold_output:
  hard: {n_trs: [">", 100]}
```

### Adding checks: `checks:` on a pipeline node

Any node in a pipeline may carry `checks:` next to its `params:`. An entry names a
**metric** from the registry, an **artifact** path template, and optional bounds that
overlay the norms for that step. Placeholders: `{node_dir}`, `{subject}`, every output
port of the node (`{out_file}`), and for apps `{fs_subject_dir}`, `{derivatives_dir}`,
`{work_dir}`. A container app evaluates its pipeline checks live, like its built-ins;
other nodes evaluate them when they finish.

```yaml
- id: fmriprep
  type: fmriprep
  data:
    params: {mode: anat_only}
    checks:
      - {step: T1.mgz, enabled: false}                       # skip a built-in
      - {step: nu.mgz, norms: {hard: {n_unique: [">", 150]}}}  # re-bound a built-in
      - step: aseg
        artifact: "{fs_subject_dir}/mri/aseg.mgz"
        metric: nifti_stats
        norms: {hard: {n_unique: [">", 30]}}
```

An artifact template may use glob wildcards (`*`, `**`) for outputs that exist once per
run; every match gets its own record, named `step[ses-01_task-x_run-2]`, judged by the
step's norms. fmriprep's built-in checks use this for the functional outputs. A
container app's built-in `CHECKS` run live while it executes; any other node's built-in
`CHECKS` are evaluated once its `run()` returns, like the checks a pipeline declares. For
an iterated node, `{node_dir}/**/<file>` matches once per iteration, and matches that
share a file name are told apart by their folder (`step[physio1]`).

Metrics: `volume_intensity`, `brain_volume`, `wm_volume`, `surface`, `thickness`,
`aseg_stats`, `output_file`, `bold_integrity` (NaN/Inf, dead volumes, negative values,
flat voxels, RF-spike volumes), `confounds_motion` (FD, DVARS, rigid-body extremes from
the confounds TSV), `fieldmap_stats`, `phasediff_delta_te` (from a GRE fieldmap JSON),
`compcor_components` (CompCor columns + variance explained), `physio_blocks`, `physio_regressors`,
`physio_clean_summary` (the physio nodes' block split, regressor TSV and cleaning summary), and the
all-purpose `nifti_stats` (shape, voxel size,
non-zero fraction, mean/std, percentiles, `n_unique`, `tsnr_median` for 4-D). Your own
metric is a decorated function in `$FMRIFLOW_HOME/addons/checks/*.py`, written by hand or
from **Library → Checkpoint metrics** (new from a scaffold, duplicate a built-in, edit, try
on a file, delete; one file per metric, named after it; built-ins are read-only). The table
lists the built-in metrics the live checks use plus your own; `GET /api/preproc/checks/metrics?all=1`
lists the parked ones too:

```python
from fmriflow.preproc.checkpoints import checkpoint_metric

@checkpoint_metric("my_metric")
def my_metric(path):
    """One line shown in the metric picker."""
    return {"value": 1.0}, {}          # (metrics, detail)
```

The node panel's **Checks** section edits all of this, and its **Try** button evaluates
a check against a finished run's node before you commit to it
(`POST /api/preproc/checks/evaluate`).

## HTTP API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/preproc/nodes` · `/nodes/{name}` · `/nodes/{name}/preflight` · `/nodes/scaffold/{kind}` | node library |
| POST | `/api/preproc/nodes` · `/nodes/import` · `/nodes/rescan` | author / import / rescan |
| GET/PUT/DELETE | `/api/preproc/pipelines/{name}` | saved pipelines |
| GET | `/api/preproc/pipelines` · `/pipelines/templates` · `/pipelines/templates/{name}` | listing + templates (each template carries `tier: bundled \| user`) |
| POST/DELETE | `/api/preproc/pipelines/templates` · `/pipelines/templates/{name}` | user templates in `$FMRIFLOW_HOME/addons/pipelines/` (save drops `run_defaults`; bundled names refused) |
| POST | `/api/preproc/pipelines/validate` · `/pipelines/run` | validate / launch |
| GET | `/api/preproc/runs` · `/runs/{id}` · `/runs/{id}/events` · `/runs/{id}/log` · `/runs/{id}/checkpoints` · `/runs/{id}/checkpoints/{i}/thumbnail` | runs |
| POST | `/api/preproc/runs/{id}/cancel` · `/resume` · `/restart` | control |
| DELETE | `/api/preproc/runs/{id}` | remove a run record |
| GET | `/api/preproc/runs/{id}/work_tree[?prefix=]` · `/node/{path}/files` · `/file` · `/pickle` | node outputs |
| GET | `/api/preproc/runs/{id}/nodes/{node_id}` · `/log` · `/inner` · `/manifest` · `/report/{rest}` · `/fs-file?rel=` · `/freeview-command` | one node of one run (the popup); `POST …/drawing` |
| GET/PUT | `/api/preproc/checks/norms` · GET `/checks/metrics` · GET `/nodes/{name}/checks` · POST `/checks/evaluate` | editable checkpoints |
| GET/PUT/DELETE | `/api/preproc/checks/metrics/{name}` · GET `/checks/metrics/scaffold` · POST `/checks/metrics/{name}/run` | user metrics: source, save (`{code}`, must register the name), delete, try on a file (`{path}`) |
| GET/POST | `/api/preproc/manifests…` · `/api/preproc/collect` · `/api/preproc/label-map` | outputs |
| WS | `/ws/preproc/{run_id}` | event stream |
