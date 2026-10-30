#!/bin/sh
# Starts the API as the unprivileged `appuser`, making sure that user can talk to the Docker
# socket (needed for the QA sandbox). The socket's group differs per platform:
#   * Linux hosts:                    usually `docker` (some GID such as 999)
#   * Docker Desktop (Windows/macOS): usually root:root (GID 0)  <- the case the old script skipped
set -eu

SOCK=/var/run/docker.sock

# setpriv (util-linux) drops privileges, loads appuser's supplementary groups from /etc/group and runs the
# command with its arguments intact. (`su -c 'exec "$@"' -- cmd` is not portable: some su versions drop the
# `--`, which silently turns the command into a no-op.)
run_as_appuser() {
  HOME=/home/appuser setpriv --reuid=appuser --regid=appuser --init-groups "$@"
}

if [ -S "$SOCK" ]; then
  gid="$(stat -c '%g' "$SOCK" 2>/dev/null || echo 0)"
  group="$(getent group "$gid" | cut -d: -f1 || true)"
  if [ -z "$group" ]; then
    group=rad-docker
    groupadd -g "$gid" "$group" 2>/dev/null || true
  fi
  usermod -aG "$group" appuser 2>/dev/null || echo "entrypoint: could not add appuser to group '$group'" >&2

  # Verify instead of assuming: can appuser actually open the socket?
  if run_as_appuser sh -c "test -r '$SOCK' && test -w '$SOCK'"; then
    echo "entrypoint: appuser can access $SOCK (group '$group', gid $gid)" >&2
  elif [ "${RAD_DOCKER_SOCKET_ROOT_FALLBACK:-0}" = "1" ]; then
    echo "entrypoint: WARNING appuser cannot access $SOCK; RAD_DOCKER_SOCKET_ROOT_FALLBACK=1 so the API runs as ROOT." >&2
    mkdir -p /workspaces /milvus-data
    exec "$@"
  else
    echo "entrypoint: WARNING appuser cannot access $SOCK (gid $gid, mode $(stat -c '%a' "$SOCK"))." >&2
    echo "entrypoint: Docker QA checks will report BLOCKED. Fix the socket permissions, or opt in to running as root" >&2
    echo "entrypoint: with RAD_DOCKER_SOCKET_ROOT_FALLBACK=1 (weaker isolation; the socket is root-equivalent anyway)." >&2
  fi
fi

chown -R appuser:appuser /workspaces /milvus-data 2>/dev/null || true
HOME=/home/appuser exec setpriv --reuid=appuser --regid=appuser --init-groups "$@"