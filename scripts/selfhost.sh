#!/bin/bash
# Recruit AI — self-hosted server on macOS, run by launchd (see
# install-selfhost.sh). Brings up, in order: Docker, the local Supabase stack,
# and the FastAPI backend, which in this mode also serves the built frontend
# and proxies /supabase. One process, one port, one origin (backend/app/selfhost.py).
#
# Ends by exec-ing uvicorn, so launchd is watching the server itself and
# restarts it if it dies.
set -u
export PATH="/usr/local/bin:/opt/homebrew/bin:$HOME/.docker/bin:/usr/bin:/bin:/usr/sbin:/sbin"

APP="$(cd "$(dirname "$0")" && pwd)"
PORT=8001
# Pinned: npx would otherwise fetch a new CLI, and with it new images, on a boot.
SUPABASE_CLI=supabase@3.0.0

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*"; }

# On a cold boot Docker Desktop takes a minute or two to accept connections.
if ! docker info >/dev/null 2>&1; then
    log "starting Docker"
    open -a Docker
    until docker info >/dev/null 2>&1; do sleep 5; done
fi

# The containers are restart=unless-stopped, so they usually come back with
# Docker on their own. This covers a `supabase stop` or a fresh install.
if [ -z "$(docker ps -q --filter name=supabase_db_recruit-ai)" ]; then
    log "starting Supabase"
    (cd "$APP" && npx --yes "$SUPABASE_CLI" start) || log "supabase start failed"
fi

# The backend starts fine without the database and then fails every request.
until curl -s -m 3 -o /dev/null http://127.0.0.1:54421/auth/v1/health; do sleep 3; done

cd "$APP/backend" || exit 1
log "starting backend on port $PORT"
# Loopback only: the tunnel connects from this machine, and 0.0.0.0 would expose
# the app, and the rate limiter's trust in loopback peers, to the whole network.
exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" --no-server-header
