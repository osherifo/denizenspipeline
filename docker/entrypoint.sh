#!/usr/bin/env bash
# fmriflow container entrypoint.
#
# Responsibilities:
#  1. If FS_LICENSE_TEXT is set, write it to FS_LICENSE so users can
#     pass the license inline (env) instead of bind-mounting a file.
#  2. Align the in-container fmriflow user's uid/gid with PUID/PGID
#     so bind-mounted files don't end up root-owned on the host.
#  3. Join the host docker socket's group, when one is mounted, so
#     fmriprep can be launched as a sibling container.
#  4. chown /workspace when its ownership is wrong, then drop
#     privileges with gosu and exec the CMD under PID 1 (tini).

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

    # Docker-out-of-docker: the socket is owned by a group whose gid
    # is a property of the *host* (commonly 'docker', but the number
    # varies per machine), and our unprivileged user is not in it. Add
    # a matching group at run time -- build time can't know the gid.
    if [ -S /var/run/docker.sock ]; then
        sock_gid="$(stat -c '%g' /var/run/docker.sock)"
        sock_group="$(getent group "$sock_gid" | cut -d: -f1)"
        if [ -z "$sock_group" ]; then
            sock_group=dockerhost
            groupadd -o -g "$sock_gid" "$sock_group" >/dev/null 2>&1 || true
        fi
        usermod -aG "$sock_group" fmriflow >/dev/null 2>&1 || true
    fi

    # Materialise the $FMRIFLOW_HOME layout if the bind mount is
    # empty on first boot. ``fmriflow init`` is idempotent.
    gosu fmriflow fmriflow init >/dev/null 2>&1 || true

    # Only recurse when ownership is actually wrong. $FMRIFLOW_HOME
    # holds the data subtree and can be hundreds of GB; walking all of
    # it on every start costs minutes and buys nothing when the uid
    # already matches. Set FMRIFLOW_FORCE_CHOWN=1 to force a full pass.
    workspace="${FMRIFLOW_HOME:-/workspace}"
    if [ "${FMRIFLOW_FORCE_CHOWN:-0}" = "1" ] \
       || [ "$(stat -c '%u' "$workspace" 2>/dev/null)" != "$PUID" ]; then
        chown -R fmriflow:fmriflow "$workspace" 2>/dev/null || true
    else
        chown fmriflow:fmriflow "$workspace" 2>/dev/null || true
    fi

    exec gosu fmriflow "$@"
fi

exec "$@"
