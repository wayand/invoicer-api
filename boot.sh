#!/bin/sh
# this script is used to boot a Docker container
# Clean Python cache files on startup
echo "Cleaning Python cache files..."
find /invoicer-api -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find /invoicer-api -name "*.pyc" -delete 2>/dev/null || true
echo "cache files cleaned"

echo "Starting application..."
uv sync --frozen

uv run flask db upgrade

echo "I am Here.........DONE while"

exec uv run gunicorn -b :5000 --access-logfile - --error-logfile - run:app
