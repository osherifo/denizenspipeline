#!/usr/bin/env bash
set -euo pipefail

eval "$(conda shell.bash hook)"
conda activate fmriprep-py310

# FreeSurfer
export FREESURFER_HOME=/usr/local/freesurfer/6.0.1
export SUBJECTS_DIR=/home/omarsh/projects/fmriprep-data-driven-analysis/data/freesurfer_subjects
export FS_LICENSE=~/fmriprep-local/fs_license.txt
set +eu
source "$FREESURFER_HOME/SetUpFreeSurfer.sh"
set -eu

# FSL
export FSLDIR=~/fsl
export PATH="$FSLDIR/bin:$PATH"
set +eu
source "$FSLDIR/etc/fslconf/fsl.sh"
set -eu

# AFNI
export PATH="$HOME/afni_bin:$PATH"

# Force unbuffered output so logs appear in real time
export PYTHONUNBUFFERED=1

fmriflow -v preproc run \
  --backend fmriprep \
  --bids-dir /home/omarsh/projects/fmriprep-playground/raw-to-bids/bids_output \
  --output-dir /home/omarsh/projects/fmriprep-playground/derivatives \
  --subject AN \
  --extra-args="--fs-no-reconall --fs-subjects-dir /home/omarsh/projects/fmriprep-data-driven-analysis/data/freesurfer_subjects" \
  --output-spaces T1w
