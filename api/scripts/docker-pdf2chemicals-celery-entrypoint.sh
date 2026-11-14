#!/bin/bash
# pdf2chemicals Celery worker. Torque is reached through torque-gateway, not from this process.
exec celery -A labsoa_website_backend worker --queues=pdf2chemicals_tasks --prefetch-multiplier=1 --autoscale=3,0 --max-tasks-per-child=1 --loglevel=INFO
