# Writing Modules

Modules are plain Python classes — no base class required. Implement the right methods, register with a decorator, and the pipeline discovers them automatically.

## Feature extractor

```python
from fmriflow.core.types import FeatureSet, StimulusData
from fmriflow.modules._decorators import feature_extractor


@feature_extractor("gpt2_surprisal")
class GPT2SurprisalExtractor:
    name = "gpt2_surprisal"
    n_dims = 1

    PARAM_SCHEMA = {
        "model_name": {
            "type": "str",
            "default": "gpt2",
            "description": "HuggingFace model name",
        },
    }

    def extract(self, stimuli: StimulusData, run_names: list[str],
                config: dict) -> FeatureSet:
        # Your extraction logic here
        ...

    def validate_config(self, config: dict) -> list[str]:
        return []
```

## Registration methods

### Decorator (recommended)

```python
from fmriflow.modules._decorators import feature_extractor

@feature_extractor("my_feature")
class MyFeatureExtractor:
    ...
```

### Entry points (for packaged modules)

```toml
# In your module's pyproject.toml
[project.entry-points."fmriflow.feature_extractors"]
my_feature = "my_module:MyFeatureExtractor"
```

### Web UI

The Module Editor in the web UI lets you write, validate, and register modules directly in the browser. Modules saved there go to `~/.fmriflow/modules/` and are loaded on server startup.

## Module types

| Type | Decorator | Scope | Required methods |
|------|-----------|-------|-----------------|
| Feature Extractor | `@feature_extractor` | subject | `extract(stimuli, run_names, config)` |
| Feature Source | `@feature_source` | subject | `load(run_names, config)` |
| Preparation Step | `@preparation_step` | subject | `apply(state, params)` |
| Analyzer | `@analyzer` | subject | `analyze(context, config)` |
| Reporter | `@reporter` | subject | `report(result, context, config)` |
| Stimulus Loader | `@stimulus_loader` | subject | `load(config)` |
| Response Loader | `@response_loader` | subject | `load(config)` |
| QA Reporter | `@qa_reporter(name, stage=...)` | subject | `report(value, config, output_dir)` |
| Group Analyzer | `@group_analyzer` | group | `analyze(group: GroupResult, config)` |
| Group Reporter | `@group_reporter` | group | `report(group: GroupResult, config)` |
| Study Analyzer | `@study_analyzer` | study | `analyze(study: StudyResult, config)` |
| Study Reporter | `@study_reporter` | study | `report(study: StudyResult, config)` |

### QA reporters (per-stage diagnostic viz)

QA reporters are bound to one pipeline stage and run automatically
when that stage finishes (and again on demand via the **Regenerate**
button in the web UI):

```python
from pathlib import Path
from fmriflow.core.types import PreparedData
from fmriflow.modules._decorators import qa_reporter


@qa_reporter("my_check", stage="prepare")
class MyPrepareCheck:
    name = "my_check"
    stage = "prepare"
    PARAM_SCHEMA = {"max_voxels": {"type": "int", "default": 1500}}

    def report(self, value: PreparedData, config: dict,
               output_dir: Path) -> dict[str, str]:
        # render whatever and save to output_dir
        return {"my_check.png": str(output_dir / "my_check.png")}
```

The orchestrator passes the resolved stage dataclass (`ResponseData`
for `responses`, `FeatureData` for `features`, `PreparedData` for
`prepare`, `ModelResult` for `model`, etc.) as `value`. Plugins are
failure-isolated — one raising doesn't kill the pipeline.

The web UI's **Module Browser → + New module** flow ([web-ui guide](web-ui.md#module-browser))
includes `qa_reporters` as a first-class creatable category: pick
the category, pick the stage, name the module, and you land in the
Monaco editor with a working template scaffold.

## Built-ins

These ship out of the box (see `fmriflow/modules/` for the source).

**Feature sources:** `compute`, `filesystem`, `cloud`, `grouped_hdf`,
`npz_concat`.

**QA reporters:**

| Stage | Plugin | Output |
|---|---|---|
| `responses` | `voxel_carpet` | voxel × time carpet (z-scored + raw) |
| `features`  | `feature_matrix` | feature-dim × time carpet (z-scored + raw, per-feature boundary lines) |
| `prepare`   | `sample_counts`, `train_test_timeline`, `delay_structure_heatmap`, `feature_row_ranges`, `zscore_check`, `responses_features_alignment` | various; the last one is a per-run X vs Y carpet pair for spotting misalignment |
| `model`     | `score_histogram`, `score_rank_curve`, `alpha_histogram`, `weight_norms_per_band` | prediction-accuracy + per-band weight summaries |

**Group analyzers:** `voxelwise_mean`, `significance_count`,
`scalar_summary`, `stacked_weights_pca` (build a PCA basis from the
cohort's weights), `external_pca_basis` (load a precomputed PCA basis
from disk).

**Group reporters:** `group_summary_html`, `group_npy_dump`,
`group_fsaverage_flatmap`.

**Study analyzers:** `group_delta`, `cohen_d_across_groups`,
`semantic_pc_correlation`, `weight_correlation_voxelwise`,
`cross_modal_prediction`, `cross_within_summary`,
`cross_group_score_pairs`.

**Study reporters:** `study_summary_html`, `study_delta_flatmap`,
`study_pc_correlation_bar`, `study_cross_within_flatmap`,
`study_score_pair_density`, `study_semantic_rgb_flatmap`,
`study_cross_modal_flatmap`, `study_amodal_flatmap`.

## PARAM_SCHEMA

Define discoverable parameters with `PARAM_SCHEMA`:

```python
PARAM_SCHEMA = {
    "window_size": {
        "type": "int",
        "default": 5,
        "min": 1,
        "max": 100,
        "description": "Sliding window size in TRs",
    },
    "model_name": {
        "type": "str",
        "default": "bert-base-uncased",
        "enum": ["bert-base-uncased", "bert-large-uncased"],
        "description": "HuggingFace model name",
    },
}
```

The schema is used by the web UI to auto-generate parameter forms and by `validate_config()` for type checking.
