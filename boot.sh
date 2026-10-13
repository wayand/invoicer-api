#!/bin/sh
# this script is used to boot a Docker container
echo "Starting application..."
flask db upgrade

echo "I am Here.........DONE while"

# --no-control-socket: gunicorn 26 would open one under $HOME, which www-data can't write
exec gunicorn -b :5000 --no-control-socket --access-logfile - --error-logfile - run:app
