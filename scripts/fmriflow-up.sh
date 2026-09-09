#!/usr/bin/env bash
#
# Bring fmriflow up with the right home and the right image.
#
# Plain `docker compose up` gets both wrong: there is no .env, so
# FMRIFLOW_HOME falls back to ~/projects/fmriflow, and the default compose
# file builds the slim image, which has no FreeSurfer or fmriprep in it.
#
#   ./scripts/fmriflow-up.sh              # full image, /mnt/data/fmriflow
#   ./scripts/fmriflow-up.sh --slim       # slim image (orchestrator only)
#   ./scripts/fmriflow-up.sh --build      # rebuild before starting
#   ./scripts/fmriflow-up.sh --down       # stop and exit (same as fmriflow-down.sh)
#   ./scripts/fmriflow-up.sh --down --logs  # ... printing the last log lines first
#   FMRIFLOW_HOME=/other/path ./scripts/fmriflow-up.sh
#
# Siblings: fmriflow-build.sh (build only), fmriflow-down.sh (stop only).
#
set -euo pipefail

FMRIFLOW_HOME="${FMRIFLOW_HOME:-/mnt/data/fmriflow}"
COMPOSE_FILE="docker-compose.full.yml"
PORT=8421
BUILD=0
DOWN=0
LOGS=0

cd "$(dirname "$0")/.."

while [ $# -gt 0 ]; do
    case "$1" in
        --slim)  COMPOSE_FILE="docker-compose.yml" ;;
        --build) BUILD=1 ;;
        --down)  DOWN=1 ;;
        --logs)  LOGS=1 ;;
        -h|--help) sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
    shift
done

export FMRIFLOW_HOME

# Options are order-independent, so decide what to do only after parsing.
if [ "$DOWN" -eq 1 ]; then
    down_args=()
    [ "$COMPOSE_FILE" = "docker-compose.yml" ] && down_args+=(--slim)
    [ "$LOGS" -eq 1 ] && down_args+=(--logs)
    exec scripts/fmriflow-down.sh "${down_args[@]}"
fi
[ "$LOGS" -eq 1 ] && { echo "error: --logs only makes sense with --down" >&2; exit 2; }

# --- preflight -------------------------------------------------------------

[ -d "$FMRIFLOW_HOME" ] || {
    echo "error: FMRIFLOW_HOME does not exist: $FMRIFLOW_HOME" >&2
    exit 1
}

# A symlink pointing outside $FMRIFLOW_HOME resolves on the host but dangles
# inside the container, and the server's path bootstrap dies on it with a
# FileExistsError that never names the offending path. Catch it here instead,
# where the message can be useful.
dangling=0
while IFS= read -r link; do
    target="$(readlink -f "$link" 2>/dev/null || true)"
    case "$target" in
        "$FMRIFLOW_HOME"/*|"$FMRIFLOW_HOME") ;;
        *)
            echo "warning: $link"
            echo "         -> $target (outside \$FMRIFLOW_HOME, will dangle in the container)"
            dangling=1
            ;;
    esac
done < <(find "$FMRIFLOW_HOME/data" -maxdepth 2 -type l 2>/dev/null)

[ "$dangling" -eq 1 ] && echo "         the server will crash-loop on startup unless these are fixed or removed."

# --- restart ---------------------------------------------------------------

# `down` first: a crash-looping container from an earlier bad invocation will
# not be replaced cleanly by `up` alone.
docker compose -f "$COMPOSE_FILE" down --remove-orphans >/dev/null 2>&1 || true

if [ "$BUILD" -eq 1 ]; then
    echo "building ($COMPOSE_FILE) ..."
    docker compose -f "$COMPOSE_FILE" build
fi

echo "starting fmriflow"
echo "  home:    $FMRIFLOW_HOME"
echo "  compose: $COMPOSE_FILE"
docker compose -f "$COMPOSE_FILE" up -d

# --- wait for it to actually serve ----------------------------------------

printf "  waiting for http://localhost:%s " "$PORT"
for _ in $(seq 1 60); do
    if curl -sf -o /dev/null "http://localhost:$PORT/" 2>/dev/null; then
        echo
        echo "ready -> http://localhost:$PORT"
        exit 0
    fi
    # A restart loop will never come up; fail fast with the real reason.
    if [ "$(docker inspect fmriflow --format '{{.State.Restarting}}' 2>/dev/null)" = "true" ]; then
        echo
        echo "error: container is restarting — startup is failing. Last log:" >&2
        docker logs fmriflow --tail 20 2>&1 | sed 's/^/  /' >&2
        exit 1
    fi
    printf "."
    sleep 2
done

echo
echo "error: did not come up within 120s. Last log:" >&2
docker logs fmriflow --tail 20 2>&1 | sed 's/^/  /' >&2
exit 1
