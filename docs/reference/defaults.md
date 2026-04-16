# Defaults

These values apply unless overridden in your config:

## Preparation

The analysis-stage preparation (trim / zscore / delay / concatenate). This is
the step that runs on already-preprocessed BOLD data before model fitting —
it is distinct from the fMRI preprocessing step (fmriprep) that produces the
BOLD data in the first place.

```yaml
preparation:
  trim_start: 5
  trim_end: 5
  delays: [1, 2, 3, 4]
  zscore: true
```

## Model

```yaml
model:
  type: bootstrap_ridge
  params:
    alphas: logspace(1,3,20)
    n_boots: 50
    single_alpha: false
    chunk_len: 40
    n_chunks: 20
```

## Reporting

```yaml
reporting:
  formats: [metrics]
  output_dir: ./results
```
