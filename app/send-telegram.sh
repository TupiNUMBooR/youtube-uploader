#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 TEXT" >&2
  exit 1
}

(( $# == 1 )) || usage

text="$1"
api="https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage"

curl -fsS \
  -d "chat_id=$TELEGRAM_CHAT_ID" \
  -d "disable_web_page_preview=false" \
  --data-urlencode "text=$text" \
  "$api" >/dev/null

echo "sent telegram message" >&2
