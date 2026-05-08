#!/usr/bin/env bash
# fmriflow container entrypoint.
#
# Responsibilities:
#  1. If FS_LICENSE_TEXT is set, write it to FS_LICENSE so users can
#     pass the license inline (env) instead of bind-mounting a file.
#  2. Align the in-container fmriflow user's uid/gid with PUID/PGID
#     so bind-mounted files don't end up root-owned on the host.
#  3. chown HOME + /workspace once, then drop privileges with gosu
#     and exec the original CMD under PID 1 (tini).

set -euo pipefail

PUID="${PUID:-1000}"
PGID="${PGID:-1000}"

# License-file shim: only write if FS_LICENSE doesn't already
# point to an existing file. Default location moves under
# $FMRIFLOW_HOME/secrets/ alongside other user secrets.
if [ -n "${FS_LICENSE_TEXT:-}" ]; then
    target="${FS_LICENSE:-${FMRIFLOW_HOME:-/workspace}/secrets/freesurfer-license.txt}"
    if [ ! -f "$target" ]; then
        mkdir -p "$(dirname "$target")"
        printf '%s\n' "$FS_LICENSE_TEXT" > "$target"
    fi
    export FS_LICENSE="$target"
fi

# uid/gid alignment + privilege drop. Only relevant when started
# as root (compose default).
if [ "$(id -u)" = "0" ]; then
    if id fmriflow >/dev/null 2>&1; then
        current_uid="$(id -u fmriflow)"
        current_gid="$(getent group fmriflow | cut -d: -f3)"
        if [ "$current_uid" != "$PUID" ]; then
            usermod -o -u "$PUID" fmriflow >/dev/null 2>&1 || true
        fi
        if [ "$current_gid" != "$PGID" ]; then
            groupmod -o -g "$PGID" fmriflow >/dev/null 2>&1 || true
        fi
    fi

    # Materialise the $FMRIFLOW_HOME layout if the bind mount is
    # empty on first boot. ``fmriflow init`` is idempotent.
    gosu fmriflow fmriflow init >/dev/null 2>&1 || true
    chown -R fmriflow:fmriflow "${FMRIFLOW_HOME:-/workspace}" 2>/dev/null || true

    exec gosu fmriflow "$@"
fi

exec "$@"
