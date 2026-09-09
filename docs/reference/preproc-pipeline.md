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
  confounds_from: fmriprep.confounds
```

| Field | Meaning |
|---|---|
| `inputs` | Named values the run request supplies. Built-in names: `subject`, `bids_dir`, `derivatives_dir`, `output_dir`, `work_dir`, `dataset`, `task`, `sessions`; anything else comes from the request's `inputs` map. |
| `nodes[].data.params` | Node parameters (see the node's schema in the Library). Schema defaults apply when a key is absent. |
| `nodes[].data.bindings` | Input port → `$inputs.<name>`. |
| `nodes[].data.literal_inputs` | Input port → fixed value (a path, a string, a list). |
| `nodes[].data.iter` | `{handle: <port>}` or `{handles: [<port>, …]}` — the node becomes a nipype `MapNode` over the list(s) arriving on those ports; `values: [...]` gives the list literally. Not available on composite nodes (put a `select` node in front). |
| `edges[]` | `sourceHandle` is an output port of `source`, `targetHandle` an input port of `target`. An input port may be fed by exactly one of: an edge, a literal, a binding. |
| `manifest.backend_node` | The node whose collector builds the base `PreprocManifest` (fmriprep, bids_app, custom_shell, a composite with `to_manifest`, or a source). |
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
field), `REQUIRED_PYTHON`, `REQUIRED_TOOLS`, `REQUIRED_ENV`, `CONTAINER`, `CHECKS`.

| Kind | Implements | Notes |
|---|---|---|
| `interface` | `run(inputs, out_dir, params) -> outputs` | plain Python; wrapped into a nipype interface automatically |
| `source` | `run(...)` with no input ports | `bids_source`, `manifest_source`, `derivatives_source` |
| `container_app` | `validate(inputs, params)`, `build_command(inputs, params, out_dir)`, `collect(inputs, params, out_dir)`, optional `checkpoint_context(...)` | runs in its own process group; set `INNER_NIPYPE_LOG = True` to stream the app's inner nipype nodes |
| `composite` | `validate(config)`, `build(config) -> nipype.Workflow`, optional `to_manifest(config, outputs)` | ports are the fields of the workflow's `inputnode` / `outputnode` |

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
 "soft_expectations": {"modal_fraction": ["<", 0.3], "n_unique": [">", 200]},
 "verdict": "bad", "reasons": ["modal_fraction=0.669 violates < 0.5"],
 "artifact": "…/sub-01/mri/nu.mgz", "t": 1757430000.0}
```

Verdicts: `ok` (all bounds hold), `suspicious` (a soft bound fails), `bad` (a hard
bound fails), `unknown` (a metric could not be computed). The norms table lives in
`fmriflow/preproc/norms.py`; a `sequence` parameter on the fmriprep node selects
sequence-specific overrides.

## HTTP API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/preproc/nodes` · `/nodes/{name}` · `/nodes/{name}/preflight` · `/nodes/scaffold/{kind}` | node library |
| POST | `/api/preproc/nodes` · `/nodes/import` · `/nodes/rescan` | author / import / rescan |
| GET/PUT/DELETE | `/api/preproc/pipelines/{name}` | saved pipelines |
| GET | `/api/preproc/pipelines` · `/pipelines/templates` · `/pipelines/templates/{name}` | listing + templates |
| POST | `/api/preproc/pipelines/validate` · `/pipelines/run` | validate / launch |
| GET | `/api/preproc/runs` · `/runs/{id}` · `/runs/{id}/events` · `/runs/{id}/log` · `/runs/{id}/checkpoints` · `/runs/{id}/checkpoints/{i}/thumbnail` | runs |
| POST | `/api/preproc/runs/{id}/cancel` · `/resume` · `/restart` | control |
| DELETE | `/api/preproc/runs/{id}` | remove a run record |
| GET | `/api/preproc/runs/{id}/work_tree` · `/node/{path}/files` · `/file` · `/pickle` | node outputs |
| GET/POST | `/api/preproc/manifests…` · `/api/preproc/collect` · `/api/preproc/label-map` | outputs |
| WS | `/ws/preproc/{run_id}` | event stream |
