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

## API

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/api/post-preproc/nodes` | list registered nodes + schemas |
| `POST` | `/api/post-preproc/graphs/validate` | validate a ReactFlow graph |
| `POST` | `/api/post-preproc/run` | start a run |
| `GET`  | `/api/post-preproc/runs` | list known runs |
| `GET`  | `/api/post-preproc/runs/{run_id}` | one run + manifest if done |
| `GET`  | `/api/post-preproc/manifests/{subject}?output_dir=…` | read a manifest from disk |
