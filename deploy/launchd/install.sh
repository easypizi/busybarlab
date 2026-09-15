#!/usr/bin/env bash
# Install launchd agents for Cursor Token Pet.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PYTHON="${PYTHON:-$REPO_ROOT/.venv/bin/python}"
MODE="${1:-}"
LOCAL_ACCOUNT="${LOCAL_ACCOUNT:-personal}"
BUSYBAR_ADDRESS="${BUSYBAR_ADDRESS:-10.0.4.20}"
ACCOUNT="${ACCOUNT:-work}"
DAEMON_URL="${DAEMON_URL:-http://127.0.0.1:8765}"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"

usage() {
  echo "Usage: $0 daemon|reporter|uninstall-daemon|uninstall-reporter"
  echo "Env: LOCAL_ACCOUNT BUSYBAR_ADDRESS ACCOUNT DAEMON_URL PYTHON"
  exit 1
}

render() {
  local src="$1"
  local dst="$2"
  sed \
    -e "s|__PYTHON__|$PYTHON|g" \
    -e "s|__REPO_ROOT__|$REPO_ROOT|g" \
    -e "s|__LOCAL_ACCOUNT__|$LOCAL_ACCOUNT|g" \
    -e "s|__BUSYBAR_ADDRESS__|$BUSYBAR_ADDRESS|g" \
    -e "s|__ACCOUNT__|$ACCOUNT|g" \
    -e "s|__DAEMON_URL__|$DAEMON_URL|g" \
    "$src" > "$dst"
}

mkdir -p "$LAUNCH_AGENTS" "$REPO_ROOT/data"

case "$MODE" in
  daemon)
    LABEL="app.busybarlab.cursor-pet"
    DST="$LAUNCH_AGENTS/$LABEL.plist"
    render "$REPO_ROOT/deploy/launchd/$LABEL.plist.template" "$DST"
    launchctl unload "$DST" 2>/dev/null || true
    launchctl load "$DST"
    echo "Loaded $DST"
    ;;
  reporter)
    LABEL="app.busybarlab.cursor-pet-reporter"
    DST="$LAUNCH_AGENTS/$LABEL.plist"
    render "$REPO_ROOT/deploy/launchd/$LABEL.plist.template" "$DST"
    launchctl unload "$DST" 2>/dev/null || true
    launchctl load "$DST"
    echo "Loaded $DST"
    ;;
  uninstall-daemon)
    DST="$LAUNCH_AGENTS/app.busybarlab.cursor-pet.plist"
    launchctl unload "$DST" 2>/dev/null || true
    rm -f "$DST"
    echo "Uninstalled daemon agent"
    ;;
  uninstall-reporter)
    DST="$LAUNCH_AGENTS/app.busybarlab.cursor-pet-reporter.plist"
    launchctl unload "$DST" 2>/dev/null || true
    rm -f "$DST"
    echo "Uninstalled reporter agent"
    ;;
  *)
    usage
    ;;
esac
