#!/bin/sh
# Self-contained, throwaway API for UI testing (started via .claude/launch.json).
#
# - Starts its own Postgres container on 127.0.0.1:5433 (no volume, removed on exit).
#   The regular dev database and your .env values are never used.
# - Seeds only the committed demo org (app/seed/orgs/demo.json).
# - Sends no real email: mail goes to a local sink that prints it to this log
#   (login 2FA codes and reset links show up there).
# - Serves the API on http://localhost:5001, which the Vue dev server expects.
set -eu

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
NAME=invoicer-claude-ui-db
DB_PORT=5433
API_PORT=5001
TMP=$(mktemp -d)
API_PID=""
MAIL_PID=""

cleanup() {
    [ -n "$API_PID" ] && kill "$API_PID" 2>/dev/null || true
    [ -n "$MAIL_PID" ] && kill "$MAIL_PID" 2>/dev/null || true
    docker rm -f "$NAME" >/dev/null 2>&1 || true
    rm -rf "$TMP"
}
trap cleanup EXIT
trap 'exit 143' INT TERM

docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d --rm --name "$NAME" \
    -e POSTGRES_PASSWORD=claude -e POSTGRES_DB=invoicer_claude_ui \
    -p 127.0.0.1:$DB_PORT:5432 postgres:18 >/dev/null

# Explicit values win over .env (python-dotenv does not override existing vars).
export FLASK_ENV=development
export FLASK_APP="$ROOT/run.py"
export DATABASE_URL="postgresql+psycopg://postgres:claude@127.0.0.1:$DB_PORT/invoicer_claude_ui"
export SECRET_KEY=ui-test-secret
export CSRF_SESSION_KEY=ui-test-csrf
export JWT_SECRET_KEY=ui-test-jwt-secret-key-with-enough-length
export SECURITY_PASSWORD_SALT=ui-test-salt
export SITE_DOMAIN=http://localhost:8080
export RATELIMIT_STORAGE_URI=memory://
export TRUSTED_PROXY_COUNT=0
export UPLOAD_FOLDER="$TMP/uploads"
export MAIL_SERVER=127.0.0.1 MAIL_PORT=1025 MAIL_USE_TLS= MAIL_USERNAME= MAIL_PASSWORD=
export MAIL_DEFAULT_SENDER=ui-test@localhost
mkdir -p "$UPLOAD_FOLDER"

cd "$ROOT"
echo "Waiting for test database..."
until uv run python -c "import psycopg,sys; psycopg.connect('postgresql://postgres:claude@127.0.0.1:$DB_PORT/invoicer_claude_ui', connect_timeout=2).close()" 2>/dev/null; do
    sleep 1
done

uv run flask db upgrade

# `flask seed` globs app/seed/orgs/*.json relative to the cwd, so run it from a
# temp dir holding only demo.json (other org files may contain real data).
mkdir -p "$TMP/seed/app/seed/orgs"
cp "$ROOT/app/seed/orgs/demo.json" "$TMP/seed/app/seed/orgs/"
(cd "$TMP/seed" && uv run --project "$ROOT" flask seed)

python3 "$ROOT/.claude/scripts/mail_sink.py" 1025 &
MAIL_PID=$!

uv run flask run --port $API_PORT --no-reload &
API_PID=$!
wait "$API_PID"
