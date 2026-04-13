#!/bin/bash
#SBATCH --job-name=fmriflow
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=12:00:00
#SBATCH --output=logs/fmriflow_%j.out
#SBATCH --error=logs/fmriflow_%j.err

# ── Single-subject pipeline run ──────────────────────────────────────────
#
# Usage:
#   sbatch slurm_single.sh experiments/my_config.yaml
#
# Expects:
#   - fmriflow.sif in /images/ (or adjust SIF path below)
#   - Experiment configs in /data/experiments/
#   - Results written to /data/results/

set -euo pipefail

SIF=/images/fmriflow.sif
CONFIG=${1:?Usage: sbatch slurm_single.sh <config.yaml>}

module load singularity 2>/dev/null || module load apptainer 2>/dev/null || true

mkdir -p logs

singularity exec \
    --writable-tmpfs \
    -B /data:/data \
    "$SIF" \
    fmriflow run "/data/experiments/$(basename "$CONFIG")"
