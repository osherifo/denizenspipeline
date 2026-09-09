#!/usr/bin/env bash
#
# Stop fmriflow. Removes the container (and any orphans) but keeps the
# image and everything under $FMRIFLOW_HOME.
#
#   ./scripts/fmriflow-down.sh            # stop
#   ./scripts/fmriflow-down.sh --slim     # same, using the slim compose file
#   ./scripts/fmriflow-down.sh --logs     # print the last log lines first
#   FMRIFLOW_HOME=/other/path ./scripts/fmriflow-down.sh
#
# Start again with ./scripts/fmriflow-up.sh.
#
set -euo pipefail

FMRIFLOW_HOME="${FMRIFLOW_HOME:-/mnt/data/fmriflow}"
COMPOSE_FILE="docker-compose.full.yml"
LOGS=0

cd "$(dirname "$0")/.."

while [ $# -gt 0 ]; do
    case "$1" in
        --slim) COMPOSE_FILE="docker-compose.yml" ;;
        --logs) LOGS=1 ;;
        -h|--help) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
    shift
done

# Compose interpolates FMRIFLOW_HOME even for `down`; export it so a missing
# .env does not produce a warning about an unset variable.
export FMRIFLOW_HOME

# Distinguish "no container" from "cannot talk to docker": an unreachable
# daemon must not be reported as a successful no-op.
if ! docker info >/dev/null 2>&1; then
    echo "error: cannot reach the docker daemon (not running, or no permission)." >&2
    exit 1
fi

state="$(docker inspect fmriflow --format '{{.State.Status}}' 2>/dev/null || true)"

if [ -z "$state" ]; then
    echo "fmriflow is not running (no container). Nothing to do."
    # Still run down so a half-created compose project is cleaned up.
    docker compose -f "$COMPOSE_FILE" down --remove-orphans >/dev/null 2>&1 || true
    exit 0
fi

if [ "$LOGS" -eq 1 ]; then
    echo "last log lines:"
    docker logs fmriflow --tail 20 2>&1 | sed 's/^/  /'
    echo
fi

echo "stopping fmriflow (was: $state)"
docker compose -f "$COMPOSE_FILE" down --remove-orphans
echo "stopped."
