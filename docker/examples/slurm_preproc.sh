#!/bin/bash
#SBATCH --job-name=fmriflow-preproc
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=24:00:00
#SBATCH --output=logs/preproc_%j.out
#SBATCH --error=logs/preproc_%j.err

# ── Run fmriprep preprocessing via fMRIflow ──────────────────────────────
#
# Usage:
#   sbatch slurm_preproc.sh sub01
#
# This runs fMRIflow inside Singularity, which in turn calls fmriprep
# (also via Singularity). Singularity-in-Singularity works natively.
#
# Adjust paths below to match your cluster layout.

set -euo pipefail

FMRIFLOW_SIF=/images/fmriflow.sif
FMRIPREP_SIF=/images/fmriprep-24.0.0.sif
SUBJECT=${1:?Usage: sbatch slurm_preproc.sh <subject_id>}

BIDS_DIR=/data/bids
OUTPUT_DIR=/data/derivatives/fmriprep
WORK_DIR=${SCRATCH:-/tmp}/fmriprep-work-${SUBJECT}
FS_LICENSE=/data/freesurfer_license.txt

module load singularity 2>/dev/null || module load apptainer 2>/dev/null || true

mkdir -p logs "$WORK_DIR"

echo "Preprocessing ${SUBJECT} with fmriprep"
echo "  fMRIflow SIF:  ${FMRIFLOW_SIF}"
echo "  fmriprep SIF:  ${FMRIPREP_SIF}"
echo "  BIDS dir:      ${BIDS_DIR}"
echo "  Output dir:    ${OUTPUT_DIR}"

singularity exec \
    --writable-tmpfs \
    -B /data:/data \
    -B /images:/images \
    -B "${WORK_DIR}:${WORK_DIR}" \
    "$FMRIFLOW_SIF" \
    fmriflow preproc run \
        --backend fmriprep \
        --subject "$SUBJECT" \
        --bids-dir "$BIDS_DIR" \
        --output-dir "$OUTPUT_DIR" \
        --work-dir "$WORK_DIR" \
        --container "$FMRIPREP_SIF" \
        --container-type singularity \
        --fs-license-file "$FS_LICENSE" \
        --output-spaces T1w MNI152NLin2009cAsym:res-2 \
        --nthreads "${SLURM_CPUS_PER_TASK}" \
        --omp-nthreads 4

echo "Cleaning up work dir: ${WORK_DIR}"
rm -rf "$WORK_DIR"
