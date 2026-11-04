#!/bin/bash
# Recruit AI: block the local Supabase ports from other machines. Run once:
#
#     sudo bash scripts/lock-down-lan.sh            # install
#     sudo bash scripts/lock-down-lan.sh --remove   # undo
#
# `supabase start` publishes its ports on every interface, so anyone on the same
# Wi-Fi or tailnet can reach:
#     54421  API gateway  /pg and /mcp run SQL as superuser with NO key
#     54422  Postgres     postgres / postgres
#     54423  Studio       the database UI
#     54424  Mailpit      captured auth mail
# Binding them to loopback is not an option here: Docker Desktop ignores both
# daemon.json's "ip" and a network's host_binding_ipv4 for these containers, and
# the Supabase CLI has no flag for it. So a pf rule drops them instead. The rule
# must exclude lo0: the backend and the backups reach these same ports over
# loopback, and the stock pf.conf does not skip it.
set -eu
[ "$(id -u)" -eq 0 ] || { echo "Run with sudo."; exit 1; }

ANCHOR=com.apple/recruitai
RULES=/etc/pf.anchors/recruitai
PLIST=/Library/LaunchDaemons/com.recruitai.pf.plist

if [ "${1:-}" = "--remove" ]; then
    launchctl bootout system "$PLIST" 2>/dev/null || true
    pfctl -a "$ANCHOR" -F all 2>/dev/null || true
    rm -f "$PLIST" "$RULES"
    echo "Removed. The Supabase ports are reachable from other machines again."
    exit 0
fi

# com.apple/* is already evaluated by the stock /etc/pf.conf, so that file stays
# untouched and a macOS update cannot silently drop the rule.
echo 'block drop in quick on ! lo0 proto { tcp, udp } from any to any port 54420:54429' > "$RULES"
chmod 644 "$RULES"

# pf rules do not survive a reboot on their own.
cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.recruitai.pf</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/sh</string><string>-c</string>
    <string>/sbin/pfctl -E; /sbin/pfctl -a $ANCHOR -f $RULES</string>
  </array>
  <key>RunAtLoad</key><true/>
</dict>
</plist>
PLISTEOF
chmod 644 "$PLIST"
launchctl bootout system "$PLIST" 2>/dev/null || true
launchctl bootstrap system "$PLIST"
sleep 1
echo "Active rule:"
pfctl -a "$ANCHOR" -sr 2>/dev/null
