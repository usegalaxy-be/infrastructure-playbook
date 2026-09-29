#!/bin/bash
. /usr/local/galaxy/galaxy-jobconf/.venv/bin/activate
exec gunicorn --workers 4 --bind 127.0.0.1:8090 flask_job_conf:app
