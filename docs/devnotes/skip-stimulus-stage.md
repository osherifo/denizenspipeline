# Skipping the Stimulus Stage for Precomputed Features

## Problem

The pipeline currently enforces this stage order:

    stimuli -> responses -> features -> preprocess -> model -> report

The **features** stage gets run names from `stimuli.runs.keys()` and passes
them to feature sources.  This means stimuli must load successfully even when
all features come from `source: filesystem` (precomputed on disk) and no
TextGrid parsing is needed.

This creates friction for users who:
- Have precomputed features and no TextGrid files at all
- Have TextGrids in an unsupported format (see `textgrid-parsing.md`)
- Are working with non-speech experiments that don't use TextGrids

## Where the coupling lives

`orchestrator.py`, features stage (~line 145):

```python
stimuli = self.ctx.get('stimuli', StimulusData)
run_names = list(stimuli.runs.keys())      # <-- requires stimuli
for feat_cfg, source in plugins['feature_sources']:
    feature_set = source.load(run_names, feat_cfg)
```

The `run_names` variable is the only thing the features stage needs from
stimuli, and only `source: compute` features actually use the TextGrid data.
Filesystem and cloud sources just use the names to locate files.

## Design options

### Option A: Derive run names from responses when stimuli are absent

If no stimuli are loaded (empty `StimulusData.runs`), fall back to getting
run names from the already-loaded `ResponseData.responses.keys()`.

Pros: Zero config changes, just works.
Cons: Implicit — might hide a real misconfiguration.

### Option B: `stimulus: skip` config value

Let users explicitly declare they don't need stimuli:

```yaml
stimulus:
  loader: skip    # or loader: none
```

The orchestrator skips the stimulus stage entirely. The features stage gets
run names from responses instead.

Pros: Explicit intent, easy to understand in config.
Cons: New loader plugin (trivial — returns empty StimulusData).

### Option C: `run_names` config key

Let users specify run names directly:

```yaml
run_names: [story1, story2, story3]
```

The features stage uses this list instead of deriving names from stimuli.

Pros: Very explicit, decouples stages completely.
Cons: Duplicates information already present in the response data.

## Recommendation

**Option B** (`stimulus: { loader: skip }`) is the cleanest:
- Explicit in config — a reader knows exactly what's happening
- No magic fallback behavior
- Trivial to implement (a no-op loader class)
- The orchestrator's fallback for run_names can use responses.keys()
  when stimuli are empty, which covers both "skip" and "loader returned
  nothing" gracefully

Combined with Option A as an internal fallback, this gives users a clean
declarative config while being resilient to edge cases.

## Implementation (DONE)

Implemented Option B + A fallback:

1. **`stimulus_loaders/skip.py`** — `SkipStimulusLoader` returns
   `StimulusData(runs={})`.  Its `validate_config` catches `source: compute`
   features and errors early.
2. **`plugins/__init__.py`** — Registered as `'skip'`.
3. **`orchestrator.py`** — Features stage falls back to
   `sorted(responses.responses.keys())` when `stimuli.runs` is empty.
4. **`docs/config-reference.md`** — Documented `skip` loader with example.
