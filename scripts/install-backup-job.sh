#!/bin/bash
# Installs the nightly backup as a launchd job (02:00, and at login to catch up
# on a night the Mac was off). Safe to re-run after changing backup-db.sh.
#
# launchd jobs cannot read ~/Desktop, so the script is copied out of the repo.
# Settings stay in ~/.config/recruit-ai/backup.env, created here as a template.
set -eu
LABEL=com.recruitai.dbbackup
SRC="$(cd "$(dirname "$0")" && pwd)/backup-db.sh"
DEST_DIR="$HOME/Library/Application Support/RecruitAI"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
CONFIG="$HOME/.config/recruit-ai/backup.env"

mkdir -p "$DEST_DIR" "$(dirname "$CONFIG")" "$HOME/recruit-ai-backups"
cp "$SRC" "$DEST_DIR/backup-db.sh"
chmod 700 "$DEST_DIR/backup-db.sh"

if [ ! -f "$CONFIG" ]; then
    cat > "$CONFIG" <<'EOF'
# Recruit AI backup settings. Holds the database password: never commit this.
DB_HOST=
DB_PORT=5432
DB_USER=
DB_PASSWORD=
# Where failure alerts go. Must be the Resend account's own address until a
# domain is verified there.
ALERT_EMAIL=
RESEND_API_KEY=
EOF
fi
chmod 600 "$CONFIG"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$DEST_DIR/backup-db.sh</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>2</integer><key>Minute</key><integer>0</integer></dict>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$HOME/recruit-ai-backups/launchd.log</string>
  <key>StandardErrorPath</key><string>$HOME/recruit-ai-backups/launchd.log</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Installed $LABEL. Settings: $CONFIG"
