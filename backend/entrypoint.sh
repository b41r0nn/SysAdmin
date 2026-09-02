#!/usr/bin/env bash
set -euo pipefail

# Run migrations and collect static assets before starting the server.
python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec gunicorn sysadmin.wsgi:application --bind 0.0.0.0:8000
