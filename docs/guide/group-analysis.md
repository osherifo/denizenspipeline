# Group Analysis

!!! warning "Phase 1 — orchestration skeleton"
    The group-scope orchestrator, CLI, and plugin protocols are in place. **No
    built-in group analyzers or reporters ship yet** — those land in Phase 2
    along with the canonical-space transforms (`to_mni_volume`,
    `to_fsaverage_surface`) that make cross-subject averaging meaningful.

    Today you can: fan out N subject pipelines from a single group config,
    collect their summaries in one place, resume failed subjects, and register
    your own `@group_analyzer` plugins. Watch this page as Phase 2 lands.

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

By default, outputs land at:

```
$FMRIFLOW_HOME/group_runs/<group_name>/
├── group_summary.json         # cross-subject summary
├── subjects/
│   ├── S1/
│   │   ├── run_summary.json   # standard per-subject summary
│   │   └── ... (per-subject artifacts)
│   ├── S2/
│   └── S3/
└── ... (group artifacts land here once Phase 2 plugins exist)
```

Override the location with `output_dir:` in the group config or by setting
`$FMRIFLOW_HOME`.

### Useful flags

| Flag | Meaning |
|---|---|
| `--resume` | Skip subjects whose `run_summary.json` already shows every stage `ok`. Failed subjects are re-run. Group stages always re-run (they're cheap and depend on all subjects). |
| `--dry-run` | Print the resolved group name, output directory, and subject list without running anything. |

## What ships in Phase 1

| Capability | Status |
|---|---|
| `fmriflow run-group` CLI subcommand | ✅ |
| `subject_template` + deep-merged `subject_overrides` | ✅ |
| Parallel subject fan-out (threads) | ✅ |
| `group_summary.json` aggregating per-subject `RunSummary` | ✅ |
| `--resume` semantics | ✅ |
| `@group_analyzer` / `@group_reporter` plugin decorators + registry | ✅ |
| Second-pass mechanism (group artifact → `external.*` in subject context → re-run analyze + report) | ✅ (wired; needs a plugin to drive it) |
| Built-in group analyzers (voxelwise mean, significance count, stacked-weights PCA, summary stats) | ⏳ Phase 2 |
| Canonical-space transforms (`to_mni_volume`, `to_fsaverage_surface`) | ⏳ Phase 2 |
| Group results UI | ⏳ Phase 4 |

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
