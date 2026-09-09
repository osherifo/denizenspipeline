#!/usr/bin/env bash
#
# Build the fmriflow image without starting it.
#
#   ./scripts/fmriflow-build.sh              # full image (fmriprep + FreeSurfer baked in)
#   ./scripts/fmriflow-build.sh --slim       # slim image (orchestrator only)
#   ./scripts/fmriflow-build.sh --no-cache   # rebuild every layer from scratch
#   ./scripts/fmriflow-build.sh --pull       # refresh the base image first
#
# Note: the full image builds on nipreps/fmriprep and is heavy (~25 GB,
# well over an hour on a cold cache). Start the result with
# ./scripts/fmriflow-up.sh, or rebuild and start in one go with
# ./scripts/fmriflow-up.sh --build.
#
set -euo pipefail

FMRIFLOW_HOME="${FMRIFLOW_HOME:-/mnt/data/fmriflow}"
COMPOSE_FILE="docker-compose.full.yml"
IMAGE="fmriflow:full"
BUILD_ARGS=()

cd "$(dirname "$0")/.."

while [ $# -gt 0 ]; do
    case "$1" in
        --slim)     COMPOSE_FILE="docker-compose.yml"; IMAGE="fmriflow:slim" ;;
        --no-cache) BUILD_ARGS+=(--no-cache) ;;
        --pull)     BUILD_ARGS+=(--pull) ;;
        -h|--help)  sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
    shift
done

# Compose interpolates FMRIFLOW_HOME while parsing the file, even for a
# build; export it so a missing .env does not warn about an unset variable.
export FMRIFLOW_HOME

# --- preflight -------------------------------------------------------------

# The build bakes the SPA bundle straight from the repo, so frontend edits
# that were never run through `npm run build` do not make it into the image.
# (mtime comparison is useless here: git checkouts touch files in arbitrary
# order. Uncommitted frontend changes are the deterministic signal.)
if command -v git >/dev/null 2>&1 && [ -d frontend/src ]; then
    pending="$(git status --porcelain -- frontend/src 2>/dev/null | head -1)"
    if [ -n "$pending" ]; then
        echo "note: frontend/src has uncommitted changes (${pending#???}, ...)."
        echo "      Run 'cd frontend && npm run build' first if you want them in the image."
    fi
fi

# --- build -----------------------------------------------------------------

echo "building $IMAGE"
echo "  compose: $COMPOSE_FILE"
[ "${#BUILD_ARGS[@]}" -gt 0 ] && echo "  args:    ${BUILD_ARGS[*]}"
start=$(date +%s)

docker compose -f "$COMPOSE_FILE" build "${BUILD_ARGS[@]}"

elapsed=$(( $(date +%s) - start ))
size="$(docker image inspect "$IMAGE" --format '{{.Size}}' 2>/dev/null || echo 0)"
size_gb="$(awk -v b="$size" 'BEGIN { printf "%.1f", b / 1e9 }')"

echo
echo "built $IMAGE (${size_gb} GB) in $((elapsed / 60))m $((elapsed % 60))s"

# A running container keeps using the old image until it is recreated.
# Only relevant when it runs the image we just built (not full vs slim).
if [ "$(docker inspect fmriflow --format '{{.State.Running}}' 2>/dev/null)" = "true" ] \
    && [ "$(docker inspect fmriflow --format '{{.Config.Image}}' 2>/dev/null)" = "$IMAGE" ]; then
    running_image="$(docker inspect fmriflow --format '{{.Image}}' 2>/dev/null)"
    new_image="$(docker image inspect "$IMAGE" --format '{{.Id}}' 2>/dev/null)"
    if [ "$running_image" != "$new_image" ]; then
        echo "note: fmriflow is running on the previous $IMAGE image."
        echo "      Restart with ./scripts/fmriflow-up.sh to pick up the new one."
    fi
fi
