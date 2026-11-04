#!/bin/bash
# Recruit AI — nightly database backup (macOS, run by launchd).
#
#     backup-db.sh           # back up, unless today's backup already exists
#     backup-db.sh --force   # back up even if it does
#     backup-db.sh --list    # show what exists
#
# Settings live in ~/.config/recruit-ai/backup.env, outside the repo, because
# they hold the database password. See scripts/install-backup-job.sh.
#
# WHAT IT DUMPS
# public (application data) and auth (the accounts). Restoring public without
# auth gives you data nobody can log in to reach. Custom format, so pg_restore
# can later restore a single table instead of all-or-nothing.
#
# WHY FAILURES SHOUT
# The Windows version of this job failed for 11+ days without anyone noticing.
# Every failure path goes through fail(), which raises a notification and
# emails the owner. A successful run is silent.
#
# Backups are written to ~/recruit-ai-backups and never inside the project
# folder: this repo's remote is public, and a dump holds every candidate record
# and auth user, one `git add -A` away from being published.
set -u
export PATH="/usr/local/bin:/opt/homebrew/bin:$HOME/.docker/bin:/usr/bin:/bin:/usr/sbin:/sbin"

CONFIG="${RECRUIT_BACKUP_CONFIG:-$HOME/.config/recruit-ai/backup.env}"
BACKUP_DIR="$HOME/recruit-ai-backups"
KEEP_DAYS=14
DB_NAME=postgres
ALERT_EMAIL=""
RESEND_API_KEY=""
# shellcheck disable=SC1090
[ -f "$CONFIG" ] && . "$CONFIG"

LOG="$BACKUP_DIR/backup.log"
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"; }

fail() {
    local reason="$1"
    log "FAILED: $reason"
    echo "Backup FAILED: $reason" >&2
    # Quotes would break out of the AppleScript string and the JSON body below,
    # and pg_dump's messages carry tabs, which JSON refuses.
    reason=$(printf '%s' "$reason" | tr '\t\n' '  ' | tr -cd '[:print:]' | tr -d '"\\')
    osascript -e "display notification \"$reason\" with title \"Recruit AI backup FAILED\" sound name \"Basso\"" 2>/dev/null
    if [ -n "$RESEND_API_KEY" ] && [ -n "$ALERT_EMAIL" ]; then
        code=$(curl -s -m 20 -o /dev/null -w '%{http_code}' https://api.resend.com/emails \
            -H "Authorization: Bearer $RESEND_API_KEY" -H 'Content-Type: application/json' \
            -d "{\"from\":\"Recruit AI <onboarding@resend.dev>\",\"to\":[\"$ALERT_EMAIL\"],\"subject\":\"Recruit AI backup FAILED\",\"text\":\"The nightly database backup failed on your Mac.\\n\\nReason: $reason\\n\\nLog: $LOG\"}")
        log "alert email: http $code"
    fi
    exit 1
}

if [ "${1:-}" = "--list" ]; then
    ls -lhT "$BACKUP_DIR"/*.dump 2>/dev/null || echo "No backups yet in $BACKUP_DIR"
    exit 0
fi

[ -f "$CONFIG" ] || fail "settings file $CONFIG is missing"
[ -n "${DB_HOST:-}" ] && [ -n "${DB_USER:-}" ] && [ -n "${DB_PASSWORD:-}" ] \
    || fail "DB_HOST, DB_USER and DB_PASSWORD must be set in $CONFIG"

# launchd also starts this at login to catch up on a night the Mac was off, so
# most of those runs have nothing to do.
if [ "${1:-}" != "--force" ] && ls "$BACKUP_DIR"/recruit-ai_"$(date +%F)"_*.dump >/dev/null 2>&1; then
    exit 0
fi

# ---- Docker ---------------------------------------------------------------
# pg_dump comes from the Supabase Postgres image, so its version matches the
# server's. Docker Desktop may simply not be running at 2am.
if ! docker info >/dev/null 2>&1; then
    log "Docker is not running, starting it"
    open -a Docker
    for _ in $(seq 1 36); do
        sleep 5
        docker info >/dev/null 2>&1 && break
    done
    docker info >/dev/null 2>&1 || fail "Docker did not start within 3 minutes"
fi

IMAGE=$(docker images --format '{{.Repository}}:{{.Tag}}' | grep 'supabase/postgres:' | head -1)
[ -n "$IMAGE" ] || fail "no Supabase Postgres image found; run npx supabase start once"

# ---- Dump -----------------------------------------------------------------
NAME="recruit-ai_$(date +%F_%H%M%S).dump"
PARTIAL="$NAME.partial"
trap 'rm -f "$BACKUP_DIR/$PARTIAL"' EXIT

ERR=$(PGPASSWORD="$DB_PASSWORD" docker run --rm -e PGPASSWORD -e PGCONNECT_TIMEOUT=30 \
    -v "$BACKUP_DIR:/out" --entrypoint pg_dump "$IMAGE" \
    -h "$DB_HOST" -p "${DB_PORT:-5432}" -U "$DB_USER" -d "$DB_NAME" \
    --schema=public --schema=auth --format=custom --compress=6 \
    --file="/out/$PARTIAL" 2>&1)
[ $? -eq 0 ] || fail "pg_dump failed: $(printf '%s' "$ERR" | tail -1 | cut -c1-200)"

SIZE=$(stat -f %z "$BACKUP_DIR/$PARTIAL" 2>/dev/null || echo 0)
[ "$SIZE" -ge 1024 ] || fail "the dump is only $SIZE bytes"

# ---- Verify ---------------------------------------------------------------
# A backup nobody has read back is a hope. This catches a truncated dump on the
# night it happens rather than the day it is needed.
TOC=$(docker run --rm -v "$BACKUP_DIR:/out" --entrypoint pg_restore "$IMAGE" --list "/out/$PARTIAL" 2>&1)
[ $? -eq 0 ] || fail "the dump is not restorable: $(printf '%s' "$TOC" | tail -1 | cut -c1-200)"
TABLES=$(printf '%s\n' "$TOC" | grep -c 'TABLE DATA')
[ "$TABLES" -ge 1 ] || fail "the dump contains no table data"

mv "$BACKUP_DIR/$PARTIAL" "$BACKUP_DIR/$NAME" || fail "could not finish writing $NAME"
chmod 600 "$BACKUP_DIR/$NAME"

# ---- Rotate ---------------------------------------------------------------
# Only reached after a verified backup, so a run of failures never eats the
# last good copies.
find "$BACKUP_DIR" -name 'recruit-ai_*.dump' -mtime +"$KEEP_DAYS" -delete

log "OK $NAME ($SIZE bytes, $TABLES tables with data)"
