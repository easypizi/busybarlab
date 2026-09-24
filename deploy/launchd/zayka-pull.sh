#!/usr/bin/env bash
# Fast-forward the local Zayka vault. Never stash, reset, or force.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ZAYKA_DIR="${ZAYKA_DIR:-$HOME/Documents/Zayka}"
LOG="$REPO_ROOT/data/zayka-pull.log"
ALERT="$REPO_ROOT/data/zayka-pull.alert"
ENV_FILE="$REPO_ROOT/services/assistant/.env"

log_line() {
  mkdir -p "$(dirname "$LOG")"
  printf '%s %s\n' "$(date +%Y-%m-%dT%H:%M:%S%z)" "$*" >> "$LOG"
}

read_env() {
  local key="$1"
  local line
  [[ -f "$ENV_FILE" ]] || return 0
  line="$(grep -E "^${key}=" "$ENV_FILE" | head -1 || true)"
  line="${line#*=}"
  line="${line%$'\r'}"
  line="${line#\"}"
  line="${line%\"}"
  printf '%s' "$line"
}

alert_once() {
  local remote="$1"
  local local_sha="$2"
  local previous token chat msg code
  previous="$(cat "$ALERT" 2>/dev/null || true)"
  if [[ "$previous" == "$remote" ]]; then
    return 0
  fi
  token="$(read_env TELEGRAM_BOT_TOKEN)"
  chat="$(read_env TELEGRAM_CHAT_ID)"
  if [[ -z "$token" || -z "$chat" ]]; then
    echo "telegram not configured" >&2
    return 0
  fi
  msg="Zayka pull is not fast-forward. Vault stayed at ${local_sha}, origin/main is ${remote}."
  code="$(
    curl -sS -o /dev/null -w '%{http_code}' --max-time 20 \
      -X POST "https://api.telegram.org/bot${token}/sendMessage" \
      --data-urlencode "chat_id=${chat}" \
      --data-urlencode "text=${msg}" \
      2>/dev/null || true
  )"
  if [[ "$code" == "200" ]]; then
    printf '%s\n' "$remote" > "$ALERT"
  else
    echo "telegram send failed http=${code:-none}" >&2
  fi
}

export GIT_TERMINAL_PROMPT=0
export GIT_SSH_COMMAND="ssh -i ${HOME}/.ssh/id_rsa -o IdentitiesOnly=yes -o BatchMode=yes"

if [[ ! -d "$ZAYKA_DIR/.git" ]]; then
  log_line "not a git repo: $ZAYKA_DIR"
  exit 1
fi

cd "$ZAYKA_DIR"

branch="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$branch" != "main" ]]; then
  log_line "refusing merge, branch is $branch"
  exit 1
fi

if ! git fetch --quiet origin main; then
  log_line "fetch failed"
  exit 1
fi

local_sha="$(git rev-parse HEAD)"
remote_sha="$(git rev-parse origin/main)"
if [[ "$local_sha" == "$remote_sha" ]]; then
  exit 0
fi

if git -c advice.diverging=false merge --ff-only origin/main; then
  rm -f "$ALERT"
  log_line "merged ${local_sha} ${remote_sha}"
  exit 0
fi

log_line "ff-only failed ${local_sha} ${remote_sha}"
alert_once "$remote_sha" "$local_sha"
exit 1
