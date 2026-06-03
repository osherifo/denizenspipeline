# Group Analysis

!!! success "All four phases shipped"
    Group analysis is feature-complete for v1: a CLI to launch group runs,
    five built-in plugins (`voxelwise_mean`, `significance_count`,
    `scalar_summary`, `stacked_weights_pca`, `group_summary_html`), a
    subject-scope `project_to_subspace` analyzer wired into the
    bidirectional second pass, and an in-browser **Group Runs** view at
    `#group-runs`.

    Canonical-space transforms (`to_mni_volume`, `to_fsaverage_surface`)
    intentionally do not ship — the built-in analyzers operate on whatever
    shape-compatible per-subject arrays you put into context, so you can
    drive them from already-aligned data (`fsaverage` from pycortex
    projection, MNI from fmriprep) today.

## When to use it

The standard `fmriflow run` command processes **one subject at a time**. That's
the right shape for fitting and inspecting individual voxelwise models. As soon
as you want to reason about results **across subjects** — averaging prediction
accuracy in MNI/`fsaverage`, computing a shared PCA basis from stacked weights,
counting how many subjects show a significant effect at each voxel — you've left
subject scope.

`fmriflow run-group` runs a *group-scope* pipeline: the same 7-stage subject
pipeline executes once per subject (in parallel), and then a new group-scope
layer reduces the per-subject results into group-level artifacts.

See `devdocs/proposals/data-processing/group-analysis.md` for the design and the
Deniz et al. 2019 worked examples this was built around.

## Concept

```text
                ┌──── subject S1 ─── stimuli → … → report
group_collect ──┼──── subject S2 ─── stimuli → … → report ──┐
                └──── subject SN ─── stimuli → … → report   ▼
                                                       group_analyze (NEW)
                                                            │
                                              (optional) subject_second_pass
                                              re-run analyze+report per subject
                                                  with group artifact bound
                                                            │
                                                            ▼
                                                       group_report (NEW)
                                                            │
                                                            ▼
                                                   group_summary.json
```

Two scopes:

- **Subject scope** — the existing 7 stages, untouched.
- **Group scope** — runs *above* subject scope. Adds `group_collect`,
  `group_analyze`, optional `subject_second_pass`, `group_report`.

## Config

A group config is a separate YAML file with a top-level `group:` block. It
contains a **`subject_template`** (the baseline subject config) and an optional
**`subject_overrides`** map keyed by subject ID.

```yaml
group: cross_subject_demo

# Either an explicit list...
subjects: [S1, S2, S3]

# ...the discovery rule (subjects_from) is coming in a later phase.

subject_template:
  experiment: my_study
  features:
    - {name: english1000}
  split:
    test_runs: [story01_validation]
  # ...the full normal subject schema goes here

subject_overrides:
  # Deep-merged into the template — only the fields that differ.
  S2:
    response:
      mask: custom_mask_S2.nii.gz

# Plugins for group_analyze / group_report (Phase 2 will ship built-ins).
# group_analyze:
#   - {name: voxelwise_mean, params: {...}}
# group_report:
#   - {name: group_summary_html}

parallel:
  max_workers: 4    # threads — preserves in-memory contexts for the second pass

# Optional. Defaults to $FMRIFLOW_HOME/group_runs/<group_name>/.
# output_dir: ./testing/cross_subject_demo
```

### Subject overrides are deep-merged

`subject_overrides[S2]` only needs to list the keys that differ from the
template. Nested dicts merge recursively; lists are replaced wholesale (same
behaviour as `inherit:` and the package defaults).

## Run it

```bash
fmriflow run-group my_group.yaml
```

By default, outputs land in a **timestamped subdirectory** under
`$FMRIFLOW_HOME/group_runs/<group_name>/`. Each invocation creates a new
`<run_id>` directory so re-runs never clobber previous results:

```
$FMRIFLOW_HOME/group_runs/<group_name>/
├── 20260530T193738Z/              # one run — ISO-ish UTC timestamp
│   ├── group_summary.json         # cross-subject summary (incl. run_id)
│   ├── group_summary.html
│   ├── group.log                  # all root-logger output from this run
│   ├── group_artifacts/
│   │   ├── group.semantic_pca_basis.npy
│   │   ├── group.semantic_pca_basis.json
│   │   └── scalars.json
│   └── subjects/
│       ├── S1/
│       │   ├── run_summary.json   # per-subject summary
│       │   ├── pipeline.log       # this subject's pipeline log
│       │   ├── prediction_accuracy_flatmap.png
│       │   ├── metrics.json
│       │   └── ...
│       ├── S2/
│       └── ...
├── 20260530T210255Z/              # a later re-run
│   └── ...
└── latest -> 20260530T210255Z     # symlink to the newest run
```

Override the parent with `output_dir:` in the group config (or by setting
`$FMRIFLOW_HOME`). The timestamped `<run_id>/` is always added underneath.

### Run logs

Every group run captures **two log streams** alongside the summaries:

- `<run_dir>/group.log` — all root-logger output during the group run.
  Catches orchestrator events plus any warnings emitted from inside
  reporters or analyzers (e.g. the `flatmap` reporter's "skipped on
  mask/voxel mismatch" warning, which used to go nowhere).
- `<run_dir>/subjects/<S>/pipeline.log` — per-subject pipeline log,
  thread-filtered so messages from sibling subjects don't bleed in
  when `parallel.max_workers > 1`.

Both are produced by the same `fmriflow.core.log_capture.capture_logs_to`
context manager — see [Writing Modules](modules.md) if you're adding a
new analyzer/reporter that should emit diagnostic warnings.

### Useful flags

| Flag | Meaning |
|---|---|
| `--resume` | When a previous run's `<run_id>/` is targeted (set via `output_dir`), skip subjects whose `run_summary.json` already shows every stage `ok`. Default behaviour with no `output_dir` override is to create a fresh timestamped run, so `--resume` is mostly relevant when you point at an existing run directory. |
| `--dry-run` | Print the resolved group name, output directory, and subject list without running anything. |

## What ships today

| Capability | Status |
|---|---|
| `fmriflow run-group` CLI subcommand | ✅ Phase 1 |
| `subject_template` + deep-merged `subject_overrides` | ✅ Phase 1 |
| Parallel subject fan-out (threads) | ✅ Phase 1 |
| `group_summary.json` aggregating per-subject `RunSummary` | ✅ Phase 1 |
| `--resume` semantics | ✅ Phase 1 |
| `@group_analyzer` / `@group_reporter` plugin decorators + registry | ✅ Phase 1 |
| Second-pass mechanism (group artifact → `external.*` → re-run analyze + report) | ✅ Phase 1 (mechanism), Phase 3 (built-in plugin) |
| `voxelwise_mean` / `significance_count` / `scalar_summary` group analyzers | ✅ Phase 2 |
| `group_summary_html` group reporter | ✅ Phase 2 |
| `stacked_weights_pca` + `project_to_subspace` (bidirectional, Deniz Fig 4) | ✅ Phase 3 |
| `SemanticSubspace` core type | ✅ Phase 3 |
| Group Runs view (`#group-runs`) — per-subject status, group-stage timings, HTML + log links | ✅ Phase 4 |
| `GET /api/group-runs` + `GET /api/group-runs/{name}/{run_id}` (legacy `/{name}` retained) | ✅ Phase 4 |
| Timestamped `<run_id>/` per invocation + `latest` symlink | ✅ Phase 4 |
| Per-group `group.log` + per-subject `pipeline.log` capture | ✅ Phase 4 |
| Canonical-space transforms (`to_mni_volume`, `to_fsaverage_surface`) | ⏳ Future (TBD) |

## Built-in group analyzers

### `voxelwise_mean`

Per-voxel mean (and SEM) of a subject-level array across the group. Writes
`group.<output_key>`, `group.<output_key>.sem`, and
`group.<output_key>.n_subjects` to the group result.

```yaml
group_analyze:
  - name: voxelwise_mean
    params:
      input_key: result.scores            # dotted path into subject ctx
      output_key: group.scores_mean       # where to write
```

Every subject must produce an array of identical shape under `input_key`
(use `fsaverage`/MNI-projected arrays for meaningful averaging).

### `significance_count`

Per-voxel count of subjects whose value passes a threshold. Modes:
`below` for p-value maps (e.g. FDR-corrected), `above` for raw accuracy
maps with a fixed cutoff. Replicates the consistency map from Deniz 2019
Fig 3c/d.

```yaml
group_analyze:
  - name: significance_count
    params:
      input_key: result.pvals
      threshold: 0.05
      mode: below                          # or 'above'
      output_key: group.n_significant
```

### `scalar_summary`

Reduces each subject's array to a single scalar (`mean` / `max` /
`median` / `none`), then reports group-level `mean`, `std`, `sem`,
`n_subjects`, and per-subject values.

```yaml
group_analyze:
  - name: scalar_summary
    params:
      input_key: result.scores
      reduce: mean                         # or 'max' / 'median' / 'none'
      output_key: group.accuracy_summary
```

The resulting dict has shape:
`{mean: float, std: float, sem: float, n_subjects: int, per_subject: {S1: 0.42, S2: 0.39, ...}}`.

### `stacked_weights_pca` (bidirectional)

Concatenates one feature's delayed-weight block from every subject along
the voxel axis and runs SVD to produce a shared K-dimensional basis. The
analyzer has `produces_subject_artifact=True`, which triggers the
orchestrator's second-pass mechanism: after the basis is built, every
subject's `analyze + report` re-runs with the basis bound into context
under `external.<binding_name>`.

```yaml
group_analyze:
  - name: stacked_weights_pca
    params:
      feature: english1000                 # name of the feature to stack (required)
      n_components: 50
      output_key: group.semantic_pca_basis
      binding_name: semantic_pca_basis     # subjects read external.<this>

# Each subject's analyze stage then receives the basis. Pair with:
subject_template:
  # ...
  analysis:
    - name: project_to_subspace
      params:
        binding: semantic_pca_basis
        output_key: analysis.semantic_pc_projection
```

The result is a `SemanticSubspace` artifact with `basis`
(`n_delayed_features × n_components`), `singular_values`, and
metadata fields (`feature`, `n_delays`, `feature_dim`,
`metadata.subjects`, `metadata.n_voxels_total`). The per-subject
`project_to_subspace` analyzer writes an
`(n_components × n_voxels_subject)` array under
`analysis.semantic_pc_projection` ready for an RGB-from-PC1-2-3 flatmap
reporter (Deniz Fig 4 style).

## Built-in group reporters

### `group_summary_html`

Renders a self-contained `group_summary.html` next to `group_summary.json`
with three sections:

- **Header** — group name, started / finished timestamps, total elapsed.
- **Subjects** — table of per-subject status, elapsed time, stage count, run dir.
- **Group stages** — table of group-stage timings (collect / fan-out / analyze / report).
- **Group artifacts** — every key on `GroupResult.artifacts` with a shape/type hint
  (`ndarray shape=(40000,) dtype=float32`, `dict(mean,sem,...)`, etc.).

```yaml
group_report:
  - name: group_summary_html
    # No params required. Optional:
    # params:
    #   output_dir: ./testing/cross_subject_demo
    #   filename: group_summary.html
```

## Writing a group analyzer

The plugin protocol mirrors the subject-scope `Analyzer`:

```python
from fmriflow.core.group_types import GroupResult
from fmriflow.modules._decorators import group_analyzer


@group_analyzer("my_summary")
class MyGroupAnalyzer:
    name = "my_summary"
    produces_subject_artifact = False    # set True to trigger the second pass

    def analyze(self, group: GroupResult, config: dict) -> None:
        # Read every subject's context/results
        scalars = []
        for sr in group.subjects:
            ctx = sr.context           # populated by fan-out; None on --resume reload
            if ctx is None:
                continue
            scalars.append(ctx.get("result").scores.mean())
        # Stash a group-level artifact
        group.put("group.mean_score", float(sum(scalars) / max(1, len(scalars))))

    def validate_config(self, config: dict) -> list[str]:
        return []
```

For plugins that produce a per-subject artifact (e.g. a shared PCA basis to
project back into each subject's space), set
`produces_subject_artifact = True` and implement `subject_bindings`:

```python
def subject_bindings(self, group: GroupResult) -> dict:
    return {"semantic_pca_basis": group.get("group.semantic_pca_basis")}
```

The orchestrator prefixes the returned keys with `external.` and re-runs
`analyze + report` for each subject with those keys in context. A subject-scope
analyzer can then read `context.get("external.semantic_pca_basis")` to consume
it.
