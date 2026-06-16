# Built-in Modules

Run `fmriflow list modules` for the full list with descriptions. Summary by category:

## Feature Extractors

| Module | Dimensions | Description |
|--------|-----------|-------------|
| `numwords` | 1 | Word count per TR |
| `numletters` | 1 | Letter count per TR |
| `numphonemes` | 1 | Phoneme count per TR |
| `word_length_std` | 1 | Std deviation of word lengths per TR |
| `english1000` | 985 | Semantic vectors from the English 1000-word space |
| `letters` | 26 | One-hot letter frequency |
| `phonemes` | ~40 | One-hot phoneme frequency |
| `word2vec` | 300 | Word2Vec embeddings |
| `bert` | 768+ | BERT contextual embeddings (configurable layer) |
| `fasttext` | 300 | FastText subword embeddings |
| `gpt2` | 768+ | GPT-2 hidden states (configurable layer) |
| `luminance` | 1 | Mean frame luminance per TR (video) |
| `motion_energy` | 1 | Frame-differencing motion energy per TR (video) |
| `clip` | 512+ | CLIP image embeddings, one row per shown image (open_clip; consumes an image sequence) |

## Feature Sources

| Module | Description |
|--------|-------------|
| `compute` | Extract from stimuli using a FeatureExtractor (default) |
| `filesystem` | Load from disk (npz, npy, hdf5) |
| `cloud` | Load from S3 via cottoncandy |
| `grouped_hdf` | Load from grouped HDF5 file |

## Stimulus Loaders

| Module | Description |
|--------|-------------|
| `textgrid` | Load from Praat TextGrid files (long, short, and chronological formats) |
| `audio` | Load audio (.wav) stimulus files |
| `video` | Load video stimulus files (metadata only) |
| `nsd` | Per-trial image references for an event-related image-viewing dataset (emits one image sequence per session) |
| `skip` | Skip stimulus loading (for pre-prepared data) |

## Response Loaders

| Module | Description |
|--------|-------------|
| `cloud` | Load from S3 |
| `local` | Load from local filesystem |
| `bids` | Load from BIDS-formatted dataset |
| `preproc` | Load from a PreprocManifest (fmriprep outputs) |
| `nsd` | Single-trial GLM betas (one pseudo-run per session), masked to an ROI and scaled; carries the 3-D ROI mask for surface reporters |

## Preparers

Analysis-stage data preparation (distinct from fMRI preprocessing / fmriprep).

| Module | Description |
|--------|-------------|
| `default` | Standard preparation pipeline (trim, zscore, delay, concatenate) |
| `pre_prepared` | Load pre-prepared X/Y matrices |
| `pipeline` | Composable preparation steps |

## Preparation Steps

For use with `type: pipeline`:

| Step | Description |
|------|-------------|
| `split` | Train/test split by run names |
| `trim` | Remove TRs from start/end of runs |
| `zscore` | Z-score normalize per run |
| `concatenate` | Concatenate runs into matrices |
| `delay` | Apply FIR delays to features |
| `mean_center` | Center features to zero mean |

## Models

| Module | Description |
|--------|-------------|
| `bootstrap_ridge` | Bootstrap ridge regression (default) |
| `himalaya_ridge` | Ridge via himalaya (GPU support) |
| `banded_ridge` | Banded ridge (per-feature-group regularization) |
| `multiple_kernel_ridge` | Multiple kernel ridge regression |
| `kernelized_banded_ridge` | Alias for `multiple_kernel_ridge` — descriptive name for the kernelized form of banded ridge |

## Reporters

| Module | Description |
|--------|-------------|
| `metrics` | Prediction accuracy metrics (JSON) |
| `flatmap` | Pycortex surface flatmaps |
| `nsd_fsaverage_flatmap` | Flatmap of func-volume scores resampled onto fsaverage (no per-subject surface registration) |
| `weights` | Model weight matrices |
| `histogram` | Accuracy distribution plots |
| `webgl` | Interactive 3D brain viewer |
