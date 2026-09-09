# Installation

## Requirements

- Python >= 3.10
- pip

The conversion, preprocessing and flattening stages shell out to external
programs (heudiconv, dcm2niix, fmriprep, FreeSurfer, …). The Docker images
bundle them; for a bare install see the
[external tools reference](../reference/external-tools.md).

## Basic install

```bash
cd fmriflow
pip install -e .
```

## Optional dependencies

Install extras for specific functionality:

```bash
pip install -e ".[cloud]"    # S3/cottoncandy support
pip install -e ".[viz]"      # pycortex flatmaps
pip install -e ".[nlp]"      # transformers, gensim
pip install -e ".[ml]"       # himalaya (banded ridge)
pip install -e ".[audio]"    # audio processing
pip install -e ".[video]"    # video/motion energy
pip install -e ".[bids]"     # BIDS utilities
pip install -e ".[all]"      # everything
```

## Environment variables

Set these to avoid hardcoded paths in configs:

| Variable | Purpose | Example |
|----------|---------|---------|
| `FMRIFLOW_DATA_DIR` | Base data directory | `/data1/experiments/fmriflow` |
| `FMRIFLOW_S3_BUCKET` | S3 bucket name | `my-shared-bucket` |
| `FMRIFLOW_OUTPUT_DIR` | Default output directory | `~/fmriflow_results` |

Reference them in YAML with `${VAR}` or `${VAR:default}`:

```yaml
paths:
  data_dir: ${FMRIFLOW_DATA_DIR}
  output_dir: ${FMRIFLOW_OUTPUT_DIR:./results}
```

## Web UI

The frontend is a React app served by the backend:

```bash
# Start the server (serves the pre-built frontend)
fmriflow serve

# Or for frontend development
cd frontend && npm install && npm run dev
```
