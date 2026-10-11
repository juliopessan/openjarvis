#!/usr/bin/env bash
# Daily Ops setup for macOS — wires the `daily-ops-mac` preset into a routine.
#
#   scripts/daily_ops_setup.sh            # schedule tasks + install launchd agent
#   scripts/daily_ops_setup.sh --init     # also (re)install the preset config
#   scripts/daily_ops_setup.sh --uninstall
#
# Re-running is safe for the launchd agent; scheduled tasks are appended, so
# clear old ones first with `jarvis scheduler list` / `jarvis scheduler cancel`.
set -euo pipefail

TZ_NAME="${DAILY_OPS_TZ:-America/Sao_Paulo}"
LABEL="com.openjarvis.scheduler"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$HOME/.openjarvis/logs"

JARVIS="$(command -v jarvis || true)"
if [[ -z "$JARVIS" ]]; then
  echo "jarvis not on PATH — activate the venv (source .venv/bin/activate) first." >&2
  exit 1
fi

if [[ "${1:-}" == "--uninstall" ]]; then
  launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
  rm -f "$PLIST"
  echo "Removed $LABEL. Scheduled tasks remain; see 'jarvis scheduler list'."
  exit 0
fi

if [[ "${1:-}" == "--init" ]]; then
  "$JARVIS" init --preset daily-ops-mac --force
fi

echo "→ Morning briefing: weekdays 07:00 ($TZ_NAME)"
"$JARVIS" digest --schedule "0 7 * * 1-5"

MONITOR_TOOLS="knowledge_search,knowledge_sql,memory_store,memory_search,think"

echo "→ Inbox monitor: weekdays 09:00, 13:00, 17:00"
"$JARVIS" scheduler create \
  "Review new emails and calendar changes since your last run. Flag anything \
urgent or needing my reply today, track open commitments in memory, and give a \
short prioritized list." \
  --type cron --value "0 9,13,17 * * 1-5" --timezone "$TZ_NAME" \
  --agent operative --tools "$MONITOR_TOOLS"

echo "→ End-of-day wrap-up: weekdays 18:30"
"$JARVIS" scheduler create \
  "Summarize what moved today using your memory notes: decisions, open items, \
and the top 3 priorities for tomorrow." \
  --type cron --value "30 18 * * 1-5" --timezone "$TZ_NAME" \
  --agent operative --tools "$MONITOR_TOOLS"

echo "→ Weekly market research: Mondays 08:00"
"$JARVIS" scheduler create \
  "Research the most relevant news of the past week on enterprise AI agents, \
multi-cloud (AWS, Azure, GCP) and AI architecture. Cite sources and highlight \
what matters for a solutions architect." \
  --type cron --value "0 8 * * 1" --timezone "$TZ_NAME" \
  --agent deep_research --tools "web_search,knowledge_search,think"

echo "→ Installing launchd agent so the scheduler survives reboots"
mkdir -p "$LOG_DIR" "$(dirname "$PLIST")"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$JARVIS</string>
        <string>scheduler</string>
        <string>start</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key><string>$(dirname "$JARVIS"):/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>$LOG_DIR/scheduler.log</string>
    <key>StandardErrorPath</key><string>$LOG_DIR/scheduler.err</string>
</dict>
</plist>
EOF
launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"

echo
echo "Done. Check with: jarvis scheduler list   |   tail -f $LOG_DIR/scheduler.log"
echo "Note: ANTHROPIC_API_KEY is not inherited by launchd; for cloud research"
echo "add it under EnvironmentVariables in $PLIST (or keep research local)."
