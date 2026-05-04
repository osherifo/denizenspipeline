# Post-Preprocessing (nipype-style nodes)

After fmriprep finishes, you often want to run a few more steps —
smoothing, masking, custom transforms — before handing volumes off to
analysis. The **Post-preproc** view lets you compose those steps as a
graph of nipype-style nodes, validate it, and run it against a subject's
preproc manifest.

## Open it

Sidebar → **Preprocessing** → **Post-preproc (nipype)**.

## Composing a graph

The view has three panels:

- **Palette** (left): every registered nipype node. Click one to drop it
  on the canvas.
- **Canvas** (center): drag nodes to reposition, drag from a node's right
  port to another node's left port to wire `out_file` → `in_file`.
- **Parameters** (right): click a node on the canvas to edit its params.

A typical graph starts with a **`preproc_run` source node** (pick a
`run_name` from the upstream manifest) and chains downstream nodes:

```
preproc_run → smooth → mask_apply
```

## Built-in nodes

| Node | Inputs | Outputs | Params |
|------|--------|---------|--------|
| `preproc_run` | — | `out_file` | `run_name` |
| `smooth` | `in_file` | `out_file` | `fwhm` (mm) |
| `mask_apply` | `in_file`, `mask_file` | `out_file` | `mask_path` (fallback) |

Authoring your own node is the same workflow as any other module — open
the **Editor**, pick category **nipype_nodes**, write a class with
`INPUTS`, `OUTPUTS`, `PARAM_SCHEMA`, and a `run(inputs, out_dir, params)`
method.

## Running

Top bar:

- **subject** — string ID for record-keeping (the source manifest is the
  authoritative input).
- **source preproc_manifest.json path** — the upstream manifest produced
  by fmriprep / preproc.
- **output_dir** — where the post-preproc run writes its outputs and
  `post_preproc_manifest.json`.
- **Validate** — server-side check (DAG, handle names, known node types).
- **Run** — start a threaded run; the panel polls until done.

Outputs land at `{output_dir}/{run_id}/<node_id>/` with a top-level
`post_preproc_manifest.json` recording params, inputs, outputs, and
per-node duration for every node that executed.

## Workflows & subworkflows

Once you have a graph that does something useful, click **Save workflow** in
the builder's top bar. The graph is written to
`~/.fmriflow/post_preproc_workflows/<name>.yaml` along with auto-derived
`inputs:` and `outputs:` — every unwired input handle and every
unconsumed output handle becomes a workflow-level port. Edit the YAML by
hand later to rename or trim ports.

**Load** brings a saved graph back onto the canvas with all node
positions, parameters, and edges preserved.

**+ Subworkflow** drops a saved workflow as a single node in the current
graph. The wrapper node's left/right handles are the workflow's declared
`inputs` and `outputs`. Wire it just like any built-in node — the runner
recurses into the inner graph at run time. Cycles
(`wf A → embeds → wf A`) raise an error rather than recursing forever.

## Iterating over runs

To run a node once per `run_name` in the source manifest (nipype's
`MapNode`), select the node and tick **Iterate over runs from source
manifest**. The runner expands the iteration over every `runs[*]` in the
upstream `PreprocManifest`, writes one output sub-directory per
iteration (`<node_id>/000/`, `<node_id>/001/`, …), and records the list
of outputs in the post-preproc manifest.

v1 limitation: iterating nodes are sinks — they can't have outgoing
edges. If you need to feed mapped outputs into a downstream node, use a
saved subworkflow as the iterating unit instead.

## Use as a workflow stage

A saved post-preproc workflow can run as a stage of the overarching
fMRIflow workflow (see [Workflows](workflows.md)). Add a `post_preproc`
entry to the workflow's `stages:` list pointing at a small stage YAML:

```yaml
# experiments/post_preproc/smooth_AN.yaml
graph: smooth_then_mask           # name of a saved post-preproc workflow
subject: sub01
source_manifest_path: ./derivatives/sub-01/preproc_manifest.json
output_dir: ./derivatives/post_preproc/sub01
bindings:
  in_file:                        # name of an exposed workflow input
    source_run: r1                # take this run's output_file from preproc
  # any_other_input:
  #   path: /abs/file.nii.gz      # or pin to a literal path
```

`bindings` translate the workflow's exposed `inputs:` ports into concrete
files. Each key looks up the saved workflow's `inputs[K] = {from:
<inner_id>.<inner_handle>}` declaration and injects a literal `_inputs`
value on that inner node — same mechanism the side panel uses, just
declared up front in YAML so a workflow run can press one button.

The Workflows view renders the post-preproc stage as a green
"Post-preproc" block between Preproc/Autoflatten and Analysis.

## API

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/api/post-preproc/nodes` | list registered nodes + schemas |
| `POST` | `/api/post-preproc/graphs/validate` | validate a ReactFlow graph |
| `POST` | `/api/post-preproc/run` | start a run |
| `GET`  | `/api/post-preproc/runs` | list known runs |
| `GET`  | `/api/post-preproc/runs/{run_id}` | one run + manifest if done |
| `GET`  | `/api/post-preproc/manifests/{subject}?output_dir=…` | read a manifest from disk |
