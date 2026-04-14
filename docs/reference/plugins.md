# Built-in Plugins

Run `fmriflow list plugins` for the full list with descriptions. Summary by category:

## Feature Extractors

| Plugin | Dimensions | Description |
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

## Feature Sources

| Plugin | Description |
|--------|-------------|
| `compute` | Extract from stimuli using a FeatureExtractor (default) |
| `filesystem` | Load from disk (npz, npy, hdf5) |
| `cloud` | Load from S3 via cottoncandy |
| `grouped_hdf` | Load from grouped HDF5 file |

## Stimulus Loaders

| Plugin | Description |
|--------|-------------|
| `textgrid` | Load from Praat TextGrid files (long, short, and chronological formats) |
| `skip` | Skip stimulus loading (for pre-prepared data) |

## Response Loaders

| Plugin | Description |
|--------|-------------|
| `cloud` | Load from S3 |
| `local` | Load from local filesystem |
| `bids` | Load from BIDS-formatted dataset |
| `preproc` | Load from a PreprocManifest (fmriprep outputs) |

## Preparers

Analysis-stage data preparation (distinct from fMRI preprocessing / fmriprep).

| Plugin | Description |
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

| Plugin | Description |
|--------|-------------|
| `bootstrap_ridge` | Bootstrap ridge regression (default) |
| `himalaya_ridge` | Ridge via himalaya (GPU support) |
| `banded_ridge` | Banded ridge (per-feature-group regularization) |
| `multiple_kernel_ridge` | Multiple kernel ridge regression |

## Reporters

| Plugin | Description |
|--------|-------------|
| `metrics` | Prediction accuracy metrics (JSON) |
| `flatmap` | Pycortex surface flatmaps |
| `weights` | Model weight matrices |
| `histogram` | Accuracy distribution plots |
| `webgl` | Interactive 3D brain viewer |
