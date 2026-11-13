#!/bin/bash
# Start trqauthd as root, then replace this process with the service user command.
# Input: TORQUE_SERVER (hostname, e.g. feynman), SVC_USER, and the image CMD.
# Output: Celery (or another command) running as SVC_USER, with trqauthd resident.
set -euo pipefail

: "${TORQUE_SERVER:?TORQUE_SERVER must be set (server name, e.g. feynman)}"
: "${SVC_USER:?SVC_USER must be set}"

SPOOL=/var/spool/torque

mkdir -p "${SPOOL}"
echo "${TORQUE_SERVER}" > "${SPOOL}/server_name"

# A restarted container can leave the previous daemon's socket behind.
rm -f /tmp/trqauthd-unix

if ! trqauthd; then
  echo "ERROR: trqauthd failed to start" >&2
  getent hosts "${TORQUE_SERVER}" >&2 || echo "ERROR: cannot resolve ${TORQUE_SERVER}" >&2
  exit 1
fi

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

exec gosu "${SVC_USER}" "$@"
