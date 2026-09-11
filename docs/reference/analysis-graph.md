# Analysis graph reference

The YAML format for analysis graphs and the HTTP API that manages them. See the
[analysis graphs guide](../guide/analysis-graphs.md) for an introduction.

## Graph file

A graph file is a mapping. It may also be wrapped under a top-level `graph:` key.

| Key | Type | Meaning |
|-----|------|---------|
| `schema_version` | int | Format version, currently `1`. |
| `name` | str | Graph name. Used as the run name when `globals.experiment` is empty. |
| `description` | str | Free text. |
| `scope` | str | `subject`, `group` or `study`. |
| `inputs` | mapping | Values supplied at run time, see below. |
| `outputs` | mapping | Reserved for sub-graphs; leave empty. |
| `globals` | mapping | Run-level configuration every node's config is built from. |
| `nodes` | list | Nodes, see below. |
| `edges` | list | Edges, see below. |
| `stages` | list | Stages always recorded in the run summary, in order, even with no node. Written by the compiler. |
| `run_defaults` | mapping | Saved run values. `run_defaults.inputs` holds input values. |

## Inputs

```yaml
inputs:
  subject: {kind: str, description: subject id}
  surface: {kind: str, required: false, default: ""}
```

| Key | Meaning |
|-----|---------|
| `kind` | A hint for forms: `str`, `file`, `dir`, `list`, ... |
| `description` | Shown next to the field. |
| `default` | Used when no value is given. |
| `required` | Defaults to `true`. A required input that is referenced and has no value is an error. |

`$inputs.<name>` strings in `globals`, node params and node literal inputs are replaced when the run
starts. A reference to an undeclared input is an error.

## Nodes

```yaml
- id: model
  type: model:bootstrap_ridge
  data:
    params: {n_boots: 50}
  position: {x: 900, y: 60}
```

| Key | Meaning |
|-----|---------|
| `id` | Unique within the graph. |
| `type` | Node type, `<category>:<module>`, or `qa_reporter:<stage>.<name>`, or `utility:<name>`. |
| `data.params` | The node's params: its module's `PARAM_SCHEMA` fields, plus `_section` for undeclared section keys. |
| `data.literal_inputs` | Constant values for input ports. |
| `position` | Layout for graphical editors; optional. |

Params that differ from a module's usual section shape:

| Node type | Param | Meaning |
|-----------|-------|---------|
| `feature_extractor:*`, `feature_source:*` | `feature_name` | Name of the feature space. |
| `feature_extractor:*` | `save_to` | Where to save the computed features. |
| `preparer:*` | `split` | The train/test split, as in the stage config's `split:` section. |
| `model:*` | all params | Become `model.params`. |

## Control nodes

| Node type | Scope | Inputs | Outputs | Params |
|-----------|-------|--------|---------|--------|
| `control:map_subjects` | group | none | `group` (GroupRun) | `subjects`, `body` or `subject_template`, `inputs`, `subject_inputs`, `subject_overrides`, `max_workers` |
| `control:subject_pass` | group | `group`, `bindings` (fan-in) | `group` | `mode`: `legacy` or `minimal` |
| `control:group` | study | none | `group` (GroupRun) | `name`, `config` |
| `control:study_groups` | study | `groups` (fan-in) | `study` (StudyRun) | none |

Group analyzers take and pass on `group`; those that bind values into subjects also output `bindings`.
Group reporters take `group`. Study analyzers take and pass on `study`; study reporters take `study`.
A control node in a graph of another scope is a validation error.

## Edges

```yaml
- {id: e1, source: prepare, sourceHandle: prepared, target: model, targetHandle: prepared}
```

`sourceHandle` is an output port of `source`; `targetHandle` is an input port of `target`. Their types
must be compatible. `any` matches everything, and a `Context` output feeds any `Context` input. A
fan-in input takes several edges, in list order.

## Run outputs

A graph run writes to `globals.reporting.output_dir`:

| File | Content |
|------|---------|
| `graph.json` | The executed graph with inputs bound. |
| `run_summary.json` | Stages with their node records, in the stage run's format. |
| `events.jsonl` | Stage and node events, including `node_skipped`. |
| intermediates, QA, reports | As in a stage run. |

## HTTP API

All paths are under `/api`.

| Method and path | Body | Result |
|-----------------|------|--------|
| `GET /analysis/nodes` | none | Every node type with ports, params, stage and error policy. `?include_hidden=true` adds hidden types. |
| `GET /analysis/nodes/{type}` | none | One node type. |
| `GET /analysis/port-types` | none | Port types and what each accepts. |
| `GET /analysis/graphs` | none | Saved graphs: name, scope, description, node types, inputs. |
| `GET /analysis/graphs/{name}` | none | One saved graph. |
| `PUT /analysis/graphs/{name}` | `{graph}` | Saves the graph and returns structural `errors`. It saves even when invalid. |
| `DELETE /analysis/graphs/{name}` | none | Deletes a saved graph. Stage configs cannot be deleted here. |
| `GET /analysis/graphs/templates` | none | Bundled and user templates with their tier and scope. |
| `GET /analysis/graphs/templates/{name}` | none | One template. |
| `POST /analysis/graphs/templates` | `{name, graph}` | Saves a user template. Returns `errors` and `warnings`; warnings flag concrete paths in node params. |
| `DELETE /analysis/graphs/templates/{name}` | none | Deletes a user template. Bundled templates return 403. |
| `POST /analysis/graphs/validate` | `{graph, inputs}` | `{ok, errors}`: structure, port types, inputs and module checks. |
| `POST /analysis/graphs/compile` | `{filename}` or `{config}` | The graph a subject stage config compiles to. |
| `POST /analysis/graphs/run` | `{graph}` or `{graph_name}`, plus `inputs` | Starts a run with its own output subdirectory and returns `{run_id}`. |

`POST /runs/from-config` also accepts a graph file path and runs it the same way.
