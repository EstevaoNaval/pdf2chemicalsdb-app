#!/bin/bash
set -e
echo "$TORQUE_SERVER_HOST" > /var/spool/torque/server_name

trqauthd

exec gosu ${PDF2CHEMICALS_WORKER_UID}:${DATA_GID} celery -A labsoa_website_backend worker --queues=pdf2chemicals_tasks --prefetch-multiplier=1 --autoscale=3,0 --max-tasks-per-child=1 --loglevel=INFO
