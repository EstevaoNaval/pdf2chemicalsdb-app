#!/bin/bash
set -euo pipefail

: "${TORQUE_SERVER_HOST:?TORQUE_SERVER_HOST must be set (server name, e.g. feynman)}"
: "${SVC_USER:?SVC_USER must be set}"

SPOOL=/var/spool/torque

# Point the Torque client commands to the server (read from $PBS_HOME/server_name)
mkdir -p "${SPOOL}"
echo "${TORQUE_SERVER_HOST}" > "${SPOOL}/server_name"

# Remove a stale socket left by a previous run of the same container (e.g. `docker restart`)
rm -f /tmp/trqauthd-unix

# trqauthd must run as root; it daemonizes and stays resident
if ! trqauthd; then
  echo "ERROR: trqauthd failed to start" >&2
  getent hosts "${TORQUE_SERVER_HOST}" >&2 || echo "ERROR: cannot resolve ${TORQUE_SERVER_HOST}" >&2
  exit 1
fi

# Wait up to ~10s for trqauthd (unix socket or loopback port 15005)
ready=0
for _ in $(seq 1 20); do
  if [ -S /tmp/trqauthd-unix ] || (exec 3<>/dev/tcp/127.0.0.1/15005) 2>/dev/null; then
    ready=1
    break
  fi
  sleep 0.5
done
if [ "${ready}" -ne 1 ]; then
  echo "ERROR: trqauthd did not become ready" >&2
  exit 1
fi

# Drop privileges: from here on, Celery and every qsub/qstat run as the service user
exec gosu "${SVC_USER}" "$@"
