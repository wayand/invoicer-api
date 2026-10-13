#!/bin/sh
# this script is used to boot a Docker container
echo "Starting application..."
flask db upgrade

echo "I am Here.........DONE while"

exec gunicorn -b :5000 --access-logfile - --error-logfile - run:app
