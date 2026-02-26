# TextGrid Parsing Issues

## Problem

The multiphase narratives TextGrids use Praat's **short format** (no `xmin =` labels,
just raw values on consecutive lines).  Neither `tgt` nor the built-in
`_SimpleTextGrid` fallback can parse them reliably:

- `tgt 1.5` crashes on short-format files with multiple tiers
  (`ValueError: invalid literal for int()`).
- `_SimpleTextGrid` (our fallback in `stimulus_utils.py`) only handles the
  **long format** — it looks for `xmin`, `xmax`, `text` labels, so it
  produces 0 tiers for short-format files.
- `praat-textgrids` (PyPI: `textgrids`) is not available for all Python
  versions / platforms.

## Status

Unresolved.  Options:

1. **Fix `_SimpleTextGrid`** to handle both long and short Praat formats.
2. **Require `praatio`** (`pip install praatio`) — it handles both formats
   and is well-maintained.
3. **Convert the multiphase TextGrids** to long format once (Praat: Save as text file)
   and sidestep the issue.

## Workaround

For experiments where features are precomputed (loaded from filesystem), the
stimulus stage can be skipped entirely — see `skip-stimulus-stage.md`.
