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
ZAYKA_DIR="${ZAYKA_DIR:-$HOME/Documents/Zayka}"
INTERVAL="${INTERVAL:-300}"
HELPER="${HELPER:-$HOME/Library/Application Support/toy_lair/Zayka Pull.app/Contents/MacOS/zayka-pull}"
LOG_DIR="${LOG_DIR:-$HOME/Library/Logs/toy_lair}"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"

usage() {
  echo "Usage: $0 daemon|reporter|zayka-pull|uninstall-daemon|uninstall-reporter|uninstall-zayka-pull"
  echo "Env: LOCAL_ACCOUNT BUSYBAR_ADDRESS ACCOUNT DAEMON_URL PYTHON ZAYKA_DIR INTERVAL"
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
    -e "s|__ZAYKA_DIR__|$ZAYKA_DIR|g" \
    -e "s|__INTERVAL__|$INTERVAL|g" \
    -e "s|__HELPER__|$HELPER|g" \
    -e "s|__LOG_DIR__|$LOG_DIR|g" \
    "$src" > "$dst"
}

build_helper() {
  local app
  app="$(dirname "$(dirname "$(dirname "$HELPER")")")"
  mkdir -p "$(dirname "$HELPER")"
  clang -Wall -Wextra -O2 -o "$HELPER" "$REPO_ROOT/deploy/launchd/zayka-pull.c"
  cp "$REPO_ROOT/deploy/launchd/ZaykaPull-Info.plist" "$app/Contents/Info.plist"
  codesign -s - --force "$app"
}

mkdir -p "$LAUNCH_AGENTS" "$REPO_ROOT/data" "$LOG_DIR"

case "$MODE" in
  daemon)
    LABEL="app.toy_lair.cursor-pet"
    DST="$LAUNCH_AGENTS/$LABEL.plist"
    render "$REPO_ROOT/deploy/launchd/$LABEL.plist.template" "$DST"
    launchctl unload "$DST" 2>/dev/null || true
    launchctl load "$DST"
    echo "Loaded $DST"
    ;;
  reporter)
    LABEL="app.toy_lair.cursor-pet-reporter"
    DST="$LAUNCH_AGENTS/$LABEL.plist"
    render "$REPO_ROOT/deploy/launchd/$LABEL.plist.template" "$DST"
    launchctl unload "$DST" 2>/dev/null || true
    launchctl load "$DST"
    echo "Loaded $DST"
    ;;
  uninstall-daemon)
    DST="$LAUNCH_AGENTS/app.toy_lair.cursor-pet.plist"
    launchctl unload "$DST" 2>/dev/null || true
    rm -f "$DST"
    echo "Uninstalled daemon agent"
    ;;
  uninstall-reporter)
    DST="$LAUNCH_AGENTS/app.toy_lair.cursor-pet-reporter.plist"
    launchctl unload "$DST" 2>/dev/null || true
    rm -f "$DST"
    echo "Uninstalled reporter agent"
    ;;
  zayka-pull)
    LABEL="app.toy_lair.zayka-pull"
    DST="$LAUNCH_AGENTS/$LABEL.plist"
    build_helper
    render "$REPO_ROOT/deploy/launchd/$LABEL.plist.template" "$DST"
    launchctl unload "$DST" 2>/dev/null || true
    launchctl load "$DST"
    echo "Loaded $DST"
    ;;
  uninstall-zayka-pull)
    DST="$LAUNCH_AGENTS/app.toy_lair.zayka-pull.plist"
    launchctl unload "$DST" 2>/dev/null || true
    rm -f "$DST"
    echo "Uninstalled zayka-pull agent"
    ;;
  *)
    usage
    ;;
esac
