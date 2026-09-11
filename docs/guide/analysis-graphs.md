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
`subject`. A graph file always runs whole on the graph engine, so `--stages`, `--resume-from` and
`--engine legacy` are refused.

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

Subject runs use the graph engine by default. `--engine legacy` or `FMRIFLOW_ENGINE=legacy` selects the
stage orchestrator. With a stage config and no engine chosen, `--stages` and `--resume-from` fall back to
the stage orchestrator automatically.

Both engines write the same run summary, events, intermediates, QA outputs and reports. The graph engine
also writes `graph.json`, the graph it executed, and records its utility nodes inside the features and
analyze stages.

## In the web server

The [Builder](web-ui.md#builder) page edits graphs on a canvas, saves them and runs them.
Saved graphs live in the analysis configs directory next to stage configs, and the config list shows
them with `format: graph`. Run views of a graph run are built from its `graph.json`. The endpoints are
listed in the [analysis graph reference](../reference/analysis-graph.md).

## Current limits

- Only `scope: subject` graph files run directly. Group and study configs run on the graph engine by
  compiling to group and study graphs (see [Group Analysis](group-analysis.md#engines)); group and study
  graph files cannot be run on their own yet.
- A graph file always runs whole; there is no partial run or resume.
