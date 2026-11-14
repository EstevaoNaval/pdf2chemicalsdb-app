#!/bin/bash
# Start trqauthd as root, then replace this process with the gateway as the service user.
# Input: TORQUE_SERVER (hostname, e.g. feynman) and SVC_PDF2CHEMICALS_PROD_CELERY_WORKER_USER.
# Output: gateway.py running as that user, with trqauthd resident.
set -euo pipefail

: "${TORQUE_SERVER:?TORQUE_SERVER must be set (server name, e.g. feynman)}"
: "${SVC_PDF2CHEMICALS_PROD_CELERY_WORKER_USER:?SVC_PDF2CHEMICALS_PROD_CELERY_WORKER_USER must be set}"

SPOOL=/var/spool/torque

# Point the Torque client commands to the server (read from $PBS_HOME/server_name).
mkdir -p "${SPOOL}"
echo "${TORQUE_SERVER}" > "${SPOOL}/server_name"

# A restarted container can leave the previous daemon's socket behind.
rm -f /tmp/trqauthd-unix

if ! trqauthd; then
  echo "ERROR: trqauthd failed to start" >&2
  getent hosts "${TORQUE_SERVER}" >&2 || echo "ERROR: cannot resolve ${TORQUE_SERVER}" >&2
  exit 1
fi

# Wait up to ~10s for trqauthd (unix socket or loopback port 15005).
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

exec gosu "${SVC_PDF2CHEMICALS_PROD_CELERY_WORKER_USER}" "$@"
