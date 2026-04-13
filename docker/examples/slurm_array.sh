#!/bin/bash
#SBATCH --job-name=fmriflow-array
#SBATCH --array=1-20
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=6:00:00
#SBATCH --output=logs/fmriflow_%A_%a.out
#SBATCH --error=logs/fmriflow_%A_%a.err

# ── Multi-subject array job ──────────────────────────────────────────────
#
# Runs the same config for multiple subjects in parallel via SLURM arrays.
#
# Usage:
#   # Create a subjects.txt with one subject ID per line:
#   echo -e "sub01\nsub02\nsub03" > subjects.txt
#   # Adjust --array=1-N to match the number of subjects
#   sbatch slurm_array.sh experiments/my_config.yaml
#
# Each array task reads one subject from subjects.txt and overrides
# the config's subject field.

set -euo pipefail

SIF=/images/fmriflow.sif
CONFIG=${1:?Usage: sbatch slurm_array.sh <config.yaml>}
SUBJECTS_FILE=${2:-subjects.txt}

SUBJECT=$(sed -n "${SLURM_ARRAY_TASK_ID}p" "$SUBJECTS_FILE")

if [ -z "$SUBJECT" ]; then
    echo "No subject found at line ${SLURM_ARRAY_TASK_ID} in ${SUBJECTS_FILE}" >&2
    exit 1
fi

module load singularity 2>/dev/null || module load apptainer 2>/dev/null || true

mkdir -p logs

echo "Running subject: ${SUBJECT} (array task ${SLURM_ARRAY_TASK_ID})"

singularity exec \
    --writable-tmpfs \
    -B /data:/data \
    "$SIF" \
    fmriflow run "/data/experiments/$(basename "$CONFIG")" --subject "$SUBJECT"
