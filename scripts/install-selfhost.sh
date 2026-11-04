#!/bin/bash
# Installs or updates the self-hosted Recruit AI server on this Mac.
#
#     scripts/install-selfhost.sh                       # http://localhost:8001
#     scripts/install-selfhost.sh https://name.ts.net   # also a public address
#     scripts/install-selfhost.sh https://name.ts.net https://app.vercel.app
#                                                       # frontend hosted elsewhere
#
# Re-run after any code change: this is the deploy step.
#
# launchd jobs cannot read ~/Desktop, so the app runs from a copy in Application
# Support and the working copy stays free to change. The database is not copied:
# it lives in Docker volumes keyed by project_id, so both copies see the same data.
set -eu
export PATH="/usr/local/bin:/opt/homebrew/bin:$HOME/Library/Python/3.9/bin:$HOME/.docker/bin:$PATH"

PUBLIC_URL="${1:-http://localhost:8001}"
PUBLIC_URL="${PUBLIC_URL%/}"
# Where visitors open the app. Differs from PUBLIC_URL when Vercel serves it.
FRONTEND_URL="${2:-$PUBLIC_URL}"
FRONTEND_URL="${FRONTEND_URL%/}"
LABEL=com.recruitai.server
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$HOME/Library/Application Support/RecruitAI/app"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOGS="$HOME/Library/Logs/RecruitAI"

echo "Building the frontend for same-origin hosting"
# Empty on purpose: supabase.js and api.js then use the page's own origin, which
# is what makes one build work on any hostname. Overrides frontend/.env.
(cd "$ROOT/frontend" && VITE_SUPABASE_URL= VITE_API_URL= npm run build >/dev/null)

echo "Copying the app to $APP"
mkdir -p "$APP/backend" "$APP/frontend" "$APP/supabase" "$LOGS"
rsync -a --delete --exclude __pycache__ "$ROOT/backend/app/" "$APP/backend/app/"
rsync -a --delete "$ROOT/frontend/dist/" "$APP/frontend/dist/"
rsync -a "$ROOT/supabase/config.toml" "$ROOT/supabase/seed.sql" "$ROOT/supabase/signing_keys.json" "$APP/supabase/"
rsync -a --delete "$ROOT/supabase/migrations/" "$APP/supabase/migrations/"
[ -f "$ROOT/supabase/.env" ] && cp "$ROOT/supabase/.env" "$APP/supabase/.env"
cp "$ROOT/backend/requirements.txt" "$APP/backend/"
cp "$ROOT/scripts/selfhost.sh" "$APP/selfhost.sh"
chmod 700 "$APP/selfhost.sh"

echo "Writing production settings"
umask 077
sed -e "s#^FRONTEND_URL=.*#FRONTEND_URL=$FRONTEND_URL#" \
    -e "s#^CORS_ORIGINS=.*#CORS_ORIGINS=$FRONTEND_URL,$PUBLIC_URL#" \
    -e "s#^GOOGLE_REDIRECT_URI=.*#GOOGLE_REDIRECT_URI=$PUBLIC_URL/api/calendar/oauth/callback#" \
    "$ROOT/backend/.env" > "$APP/backend/.env"
umask 022

echo "Installing Python packages"
[ -x "$APP/backend/.venv/bin/python" ] || uv venv --quiet --python 3.12 "$APP/backend/.venv"
uv pip install --quiet --python "$APP/backend/.venv/bin/python" -r "$APP/backend/requirements.txt"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/caffeinate</string>
    <string>-is</string>
    <string>/bin/bash</string>
    <string>$APP/selfhost.sh</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>15</integer>
  <key>StandardOutPath</key><string>$LOGS/server.log</string>
  <key>StandardErrorPath</key><string>$LOGS/server.log</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Installed. Backend $PUBLIC_URL, frontend $FRONTEND_URL (logs: $LOGS/server.log)"
