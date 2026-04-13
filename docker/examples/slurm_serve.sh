#!/bin/bash
#SBATCH --job-name=fmriflow-ui
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=8:00:00
#SBATCH --output=logs/fmriflow_serve_%j.out

# ── Run the fMRIflow web UI on a cluster node ────────────────────────────
#
# Usage:
#   sbatch slurm_serve.sh
#
# After the job starts, check the output log for the node name, then
# SSH tunnel from your laptop:
#
#   ssh -L 8421:<node>:8421 user@cluster
#   # Open http://localhost:8421 in your browser

set -euo pipefail

SIF=/images/fmriflow.sif
PORT=8421

module load singularity 2>/dev/null || module load apptainer 2>/dev/null || true

mkdir -p logs

NODE=$(hostname)
echo "==========================================="
echo "  fMRIflow web UI starting on ${NODE}:${PORT}"
echo ""
echo "  SSH tunnel from your laptop:"
echo "    ssh -L ${PORT}:${NODE}:${PORT} ${USER}@$(hostname -d)"
echo ""
echo "  Then open: http://localhost:${PORT}"
echo "==========================================="

singularity exec \
    --writable-tmpfs \
    -B /data:/data \
    "$SIF" \
    fmriflow serve \
        --host 0.0.0.0 \
        --port "$PORT" \
        --configs-dir /data/experiments \
        --results-dir /data/results \
        --derivatives-dir /data/derivatives
