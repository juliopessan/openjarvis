#!/usr/bin/env bash
# Daily Ops setup for macOS — wires the `daily-ops-mac` preset into a routine.
#
#   scripts/daily_ops_setup.sh            # schedule tasks + install launchd agents
#   scripts/daily_ops_setup.sh --init     # also (re)install the preset config
#   scripts/daily_ops_setup.sh --uninstall
#
# Installs two always-on launchd agents:
#   com.openjarvis.scheduler — runs the scheduled routine below
#   com.openjarvis.listen    — clap twice, then speak to Jarvis
#
# Re-running is safe for the launchd agents; scheduled tasks are appended, so
# clear old ones first with `jarvis scheduler list` / `jarvis scheduler cancel`.
set -euo pipefail

TZ_NAME="${DAILY_OPS_TZ:-America/Sao_Paulo}"
AGENTS_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$HOME/.openjarvis/logs"
LABELS=(com.openjarvis.scheduler com.openjarvis.listen)

JARVIS="$(command -v jarvis || true)"
if [[ -z "$JARVIS" ]]; then
  echo "jarvis not on PATH — activate the venv (source .venv/bin/activate) first." >&2
  exit 1
fi

if [[ "${1:-}" == "--uninstall" ]]; then
  for label in "${LABELS[@]}"; do
    launchctl bootout "gui/$(id -u)" "$AGENTS_DIR/$label.plist" 2>/dev/null || true
    rm -f "$AGENTS_DIR/$label.plist"
  done
  echo "Removed launchd agents. Scheduled tasks remain; see 'jarvis scheduler list'."
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

# install_agent LABEL LOG_NAME JARVIS_ARGS... — always-on launchd agent
install_agent() {
  local label="$1" log="$2" plist="$AGENTS_DIR/$1.plist" args="" arg
  shift 2
  for arg in "$JARVIS" "$@"; do
    args+="        <string>$arg</string>"$'\n'
  done
  mkdir -p "$LOG_DIR" "$AGENTS_DIR"
  cat > "$plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>$label</string>
    <key>ProgramArguments</key>
    <array>
${args}    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key><string>$(dirname "$JARVIS"):/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>$LOG_DIR/$log.log</string>
    <key>StandardErrorPath</key><string>$LOG_DIR/$log.err</string>
</dict>
</plist>
PLIST
  launchctl bootout "gui/$(id -u)" "$plist" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$plist"
}

echo "→ Installing scheduler agent (survives reboots)"
install_agent com.openjarvis.scheduler scheduler scheduler start

echo "→ Installing clap-to-talk listener"
install_agent com.openjarvis.listen listen listen

echo
echo "Done. Clap twice near the Mac and Jarvis will answer."
echo "macOS asks for Microphone access the first time — allow it."
echo "Logs: $LOG_DIR   |   Tasks: jarvis scheduler list"
echo "Note: ANTHROPIC_API_KEY is not inherited by launchd; for cloud research"
echo "add it under EnvironmentVariables in $AGENTS_DIR/com.openjarvis.scheduler.plist."
