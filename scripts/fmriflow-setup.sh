#!/usr/bin/env bash
#
# First-time interactive setup: ask where FMRIFLOW_HOME should live,
# persist it to .env (so plain `docker compose` works from then on),
# build the image, and run in the FOREGROUND (Ctrl-C stops it).
#
#   ./scripts/fmriflow-setup.sh           # full image
#   ./scripts/fmriflow-setup.sh --slim    # slim image (orchestrator only)
#
# For day-to-day restarts use ./scripts/fmriflow-up.sh instead.
#
set -euo pipefail

COMPOSE_FILE="docker-compose.full.yml"

cd "$(dirname "$0")/.."

while [ $# -gt 0 ]; do
    case "$1" in
        --slim) COMPOSE_FILE="docker-compose.yml" ;;
        -h|--help) sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
    shift
done

# --- ask for the home directory --------------------------------------------

# Default: current .env value if there is one, else a sensible generic spot.
default_home="$HOME/fmriflow"
if [ -f .env ]; then
    existing="$(sed -n 's/^FMRIFLOW_HOME=//p' .env | tail -1)"
    [ -n "$existing" ] && default_home="$existing"
fi

printf "Where should fMRIflow keep its data (FMRIFLOW_HOME)?\n"
printf "This directory holds configs, BIDS data, derivatives and results.\n"
read -r -e -p "path [$default_home]: " answer
FMRIFLOW_HOME="${answer:-$default_home}"
# Expand a leading ~
case "$FMRIFLOW_HOME" in "~"*) FMRIFLOW_HOME="$HOME${FMRIFLOW_HOME#\~}" ;; esac

if [ ! -d "$FMRIFLOW_HOME" ]; then
    read -r -p "$FMRIFLOW_HOME does not exist. Create it? [Y/n] " yn
    case "${yn:-Y}" in
        [Yy]*) mkdir -p "$FMRIFLOW_HOME" ;;
        *) echo "aborted."; exit 1 ;;
    esac
fi

# --- persist to .env so plain `docker compose` gets the same home ----------

if [ -f .env ] && grep -q '^FMRIFLOW_HOME=' .env; then
    sed -i "s|^FMRIFLOW_HOME=.*|FMRIFLOW_HOME=$FMRIFLOW_HOME|" .env
else
    printf 'FMRIFLOW_HOME=%s\n' "$FMRIFLOW_HOME" >> .env
fi
echo "wrote FMRIFLOW_HOME=$FMRIFLOW_HOME to .env"
export FMRIFLOW_HOME

# --- preflight -------------------------------------------------------------

# A symlink pointing outside $FMRIFLOW_HOME resolves on the host but dangles
# inside the container, where the server's path bootstrap dies on it with an
# unhelpful FileExistsError. Catch it here with a useful message.
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

[ "$dangling" -eq 1 ] && {
    echo "         the server will crash-loop on startup unless these are fixed or removed."
    read -r -p "continue anyway? [y/N] " yn
    case "${yn:-N}" in [Yy]*) ;; *) echo "aborted."; exit 1 ;; esac
}

# FreeSurfer license: the full image expects it under secrets/.
if [ "$COMPOSE_FILE" = "docker-compose.full.yml" ] \
    && [ ! -f "$FMRIFLOW_HOME/secrets/freesurfer-license.txt" ] \
    && [ -z "${FS_LICENSE_TEXT:-}" ]; then
    echo "note: no FreeSurfer license at $FMRIFLOW_HOME/secrets/freesurfer-license.txt"
    echo "      preprocessing (fmriprep) will fail without one; the UI itself will run."
fi

# --- build and run (foreground) --------------------------------------------

echo "building ($COMPOSE_FILE) ..."
docker compose -f "$COMPOSE_FILE" build

# Remove any leftover container from an earlier bad invocation.
docker compose -f "$COMPOSE_FILE" down --remove-orphans >/dev/null 2>&1 || true

echo "starting fmriflow (foreground; Ctrl-C to stop)"
echo "  home:    $FMRIFLOW_HOME"
echo "  compose: $COMPOSE_FILE"
echo "  url:     http://localhost:8421"
exec docker compose -f "$COMPOSE_FILE" up
