# Analysis graphs

A subject analysis is a graph: nodes are modules, edges carry data from one module to the next. A graph
file states exactly which modules run and what feeds what. An analysis that does not fit the fixed
stimuli, responses, features, prepare, model, analyze, report chain is simply a different graph, for
example two feature spaces feeding one model, or the same reporter twice with different settings.

Stage-section configs keep working. `fmriflow run experiment.yaml` compiles the config into the
equivalent graph and runs that.

## Concepts

| Term | Meaning |
|------|---------|
| Node type | A module as a graph node, named `<category>:<module>`, for example `model:bootstrap_ridge` or `reporter:flatmap`. Every registered module is a node type, add-on modules included. |
| Node | One use of a node type, with its own id, params and connections. A type may appear several times. |
| Port | A named, typed input or output, for example a model's `prepared` input (`PreparedData`) and `result` output (`ModelResult`). |
| Graph | Nodes, edges, graph inputs and globals. |
| Template | A saved graph used as a starting point. |

Stages remain as labels. Each node type belongs to a stage, which groups its nodes in the run summary and
the dashboard.

## Running a graph

```bash
fmriflow run my_analysis.yaml \
  --input subject=sub01 \
  --input responses_path=/data/responses/sub01.hdf \
  --input 'test_runs=[run01, run02]' \
  --input output_dir=/data/results/sub01
```

`--input` values are parsed as YAML, so lists and numbers work. `--subject` fills a graph input named
`subject`. A graph file always runs whole, so `--stages` and `--resume-from` are refused.

Check a graph without running it:

```bash
fmriflow graph validate my_analysis.yaml --input subject=sub01
```

Validation reports unknown node types and ports, cycles, edges whose port types don't match, required
inputs nothing feeds, graph inputs without a value, and each module's own config checks.

## Starting from a stage config

```bash
fmriflow graph compile experiment.yaml -o experiment_graph.yaml
```

The compiled graph reproduces the stage run: it carries the whole resolved config as `globals`, and its
node ids match the node ids of a stage run, so run summaries and events line up.

## A graph file

This graph fits a ridge model on precomputed features and writes metrics:

```yaml
schema_version: 1
name: my_analysis
scope: subject
inputs:
  subject: {kind: str, description: subject id}
  responses_path: {kind: file}
  features_dir: {kind: dir}
  test_runs: {kind: list}
  output_dir: {kind: dir}
globals:
  experiment: my_experiment
  subject: $inputs.subject
  reporting: {output_dir: $inputs.output_dir}
nodes:
  - id: stimuli
    type: stimulus_loader:skip
  - id: responses
    type: response_loader:local
    data: {params: {path: $inputs.responses_path}}
  - id: semantic
    type: feature_source:filesystem
    data: {params: {path: $inputs.features_dir, feature_name: semantic}}
  - id: bundle
    type: utility:bundle_features
  - id: prepare
    type: preparer:default
    data: {params: {delays: [1, 2, 3, 4], split: {test_runs: $inputs.test_runs}}}
  - id: model
    type: model:bootstrap_ridge
    data: {params: {n_boots: 50}}
  - id: context
    type: utility:collect_context
  - id: metrics
    type: reporter:metrics
edges:
  - {id: e1, source: stimuli, sourceHandle: stimuli, target: semantic, targetHandle: stimuli}
  - {id: e2, source: responses, sourceHandle: responses, target: semantic, targetHandle: responses}
  - {id: e3, source: semantic, sourceHandle: feature, target: bundle, targetHandle: features}
  - {id: e4, source: responses, sourceHandle: responses, target: prepare, targetHandle: responses}
  - {id: e5, source: bundle, sourceHandle: features, target: prepare, targetHandle: features}
  - {id: e6, source: prepare, sourceHandle: prepared, target: model, targetHandle: prepared}
  - {id: e7, source: model, sourceHandle: result, target: context, targetHandle: result}
  - {id: e8, source: context, sourceHandle: context, target: metrics, targetHandle: context}
```

### Inputs

`inputs` declares the values given at run time. Every `$inputs.<name>` string in `globals`, node params
or literal inputs is replaced by that value. An input with a `default` uses it when no value is given,
and `required: false` lets an input stay empty. A saved graph can keep values in `run_defaults.inputs`;
values given at run time win.

### Globals

`globals` holds the run-level configuration: `experiment`, `subject`, `subject_config` (the pycortex
surface and transform), `reporting.output_dir`, and anything a module reads outside its own section.

Each node's configuration is the globals with the node's own section replaced by its params. A
`model:*` node's params become `model.params`, a `preparer:*` node's params become `preparation`, and a
`reporter:*` node's params become that reporter's settings. That is why the same module can appear twice
with different params. Section keys a module reads but does not declare go under the reserved
`_section` param, for example the TextGrid loader's `textgrid_dir` and `trfile_dir`.

### Nodes and edges

A node has an `id`, a `type`, `data.params` and an optional `position` for graphical layout. An edge
connects an output port (`source`, `sourceHandle`) to an input port (`target`, `targetHandle`). An output
can feed any number of inputs. A fan-in input takes several edges in order. For example,
`utility:bundle_features` takes one edge per feature space, and the feature matrix columns follow edge
order.

## Ports by category

| Node type | Inputs | Outputs | When it fails |
|-----------|--------|---------|---------------|
| `stimulus_loader:*` | none | `stimuli` (StimulusData) | the run stops |
| `response_loader:*` | none | `responses` (ResponseData) | the run stops |
| `feature_extractor:*` | `stimuli`, `responses` (optional) | `feature` (FeatureSet) | the run stops |
| `feature_source:*` | `stimuli` and `responses`, both optional | `feature` (FeatureSet) | the run stops |
| `utility:bundle_features` | `features` (FeatureSet, fan-in) | `features` (FeatureData) | the run stops |
| `preparer:*` | `responses`, `features` (FeatureData) | `prepared` (PreparedData) | the run stops |
| `model:*` | `prepared` | `result` (ModelResult) | the run stops |
| `utility:collect_context` | `seed`, `stimuli`, `responses`, `features`, `prepared`, `result`, `bindings`, all optional | `context` (Context) | the run stops |
| `analyzer:*` | `context` (fan-in) | `context` | isolated: its input passes through |
| `reporter:*` | `context` (fan-in) | `artifacts` | isolated: the report stage fails only if every reporter fails |
| `qa_reporter:<stage>.<name>` | `value`, the stage's output | `artifacts` | isolated |
| `utility:pick` | `context` | `value`, the context key named by the `key` param | the run stops |

Analyzers and reporters work on a Context, the same named keys (`result`, `analysis.<name>`, ...) they
read and write in a stage run. `utility:collect_context` gathers typed values into one. The catalog
also lists `group_*` and `study_*` node types; they do not run in graphs yet.

The web server lists every node type with its ports and params at `GET /api/analysis/nodes`.

## Templates

Two templates ship with the package:

| Template | What it does |
|----------|--------------|
| `analyze` | TextGrid stimuli, word and letter rate features, bootstrap ridge, then metrics, a score histogram and a flatmap. |
| `analyze_precomputed_features` | Responses name the runs, features load from per-run files, then bootstrap ridge and the same reports. |

Their dataset-specific values (subject, paths, test runs, output directory) are graph inputs. User
templates live in `$FMRIFLOW_HOME/addons/analysis_pipelines/`. They cannot reuse a bundled name and never
carry `run_defaults`.

## Engines

All runs use the graph engine. Stage configs compile to graphs, and `--stages` or `--resume-from` run only
those stages of the compiled graph, continuing the checkpointed context. The stage orchestrators were
retired; `--engine legacy` and `FMRIFLOW_ENGINE=legacy` are still accepted, log a warning, and run on the
graph engine.

The run summary, events, intermediates, QA outputs and reports keep the format they had. The graph engine
also writes `graph.json`, the graph it executed, and records its utility nodes inside the features and
analyze stages.

## In the web server

The [Builder](web-ui.md#builder) page edits graphs on a canvas, saves them and runs them.
Saved graphs live in the analysis configs directory next to stage configs, and the config list shows
them with `format: graph`. Run views of a graph run are built from its `graph.json`. The endpoints are
listed in the [analysis graph reference](../reference/analysis-graph.md).

## Group and study graphs

A group graph fans out over subjects, and a study graph over groups. Both run with the same commands as
subject graphs:

```bash
fmriflow run group_graph.yaml --input 'subjects=[sub01, sub02]' --run-id first
fmriflow run group_graph.yaml --resume
```

Runs land in `<output_dir>/<run_id>/`, exactly like `run-group` and `run-study` (which also accept graph
files). Group and study configs compile to the same kind of graph, see [Group Analysis](group-analysis.md#engines).

A **group graph** starts with a `control:map_subjects` node and passes a `GroupRun` along group analyzers
to group reporters:

| Param | Meaning |
|-------|---------|
| `subjects` | Subject ids. |
| `body` | The subject graph run for each subject: a graph file, a saved graph or a template name. |
| `inputs` | Values for the body's inputs for every subject. `{subject}` in a value becomes the subject id, e.g. `responses_path: /data/responses/{subject}.hdf`. |
| `subject_inputs` | Values for one subject, `{sub01: {test_runs: [run03]}}`; they win over `inputs`. |
| `subject_template`, `subject_overrides` | Instead of `body`: a stage config for every subject and per-subject deep merges, as in a group config. |
| `max_workers` | Subjects that run at the same time. |

The body's `subject` input is filled with the subject id, and its reporting output directory is set to
`subjects/<subject>/` inside the group run. When a group analyzer binds values into subjects
(`produces_subject_artifact`), connect its `bindings` output to a `control:subject_pass` node before the
reporters: it re-runs each subject's analyze and report stages with the bound values (`mode: legacy`), or
only modules marked `binding_consumer` (`mode: minimal`).

A **study graph** has one `control:group` node per group (`name`, the study-scope label, and `config`, a
group config or a group graph file), a `control:study_groups` node collecting them in connection order,
then study analyzers and reporters passing a `StudyRun`.

Two bundled templates start these graphs: `group_mean` runs a subject graph per subject and maps mean
accuracy and a per-voxel count, and `study_group_delta` compares two groups.

## Current limits

- Graph files of every scope run whole; `--resume` on group and study graph files skips finished subjects,
  but there is no partial run of a subject graph.
- A graph file always runs whole; there is no partial run or resume.
