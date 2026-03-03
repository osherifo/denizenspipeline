# Run Name Mismatches Between Stages

## Problem

The preprocessor intersects response run names with feature run names:

```python
all_runs = sorted(
    set(responses.responses.keys()) & set(feature_runs)
)
```

If these sets don't overlap, `all_runs` is empty and `np.vstack([])`
crashes with "need at least one array to concatenate".

This happens when response data and stimulus data use different naming
conventions for the same stories.  Example:

| Response file (multiphase HDF) | Stimulus TextGrid |
|----------------------------|-------------------|
| `story_01`                 | `story02` |
| `story_02`                 | `story11` |
| ...                        | ... |

## Solution: `run_map` in response config

We added a `run_map` dict to `LocalResponseLoader` that renames response
keys after loading:

```yaml
response:
  run_map:
    story_01: story02
    story_02: story11
    ...
```

Keys = names from the reader, values = names the pipeline expects (matching
stimulus/feature names).  Unmapped names pass through unchanged.

Lives in `local.py` lines 46-50.  Applied before mask indexing.

## How the mapping was determined

Both sets of names are alphabetically ordered — the multiphase HDF files use
`story_01` through `story_11` which correspond to the 11 TextGrid files
sorted alphabetically.
