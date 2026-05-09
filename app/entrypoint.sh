#!/usr/bin/env bash
set -euo pipefail

WORKSPACE=/app/workspace
LAST_RUN_FILE=/app/workspace/uploaded.epoch
PERIOD_SECONDS="${PERIOD_SECONDS:-86400}"
ERROR_RESET_THRESHOLD="${ERROR_RESET_THRESHOLD:-10}"
ERRORS_IN_ROW=0
LOGGED_NEXT_RUN=0

# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------

now() { date -u +%s; }

should_run() {
  local last
  [[ -f "$LAST_RUN_FILE" ]] || return 0
  last="$(cat "$LAST_RUN_FILE")"
  (( $(now) - last >= PERIOD_SECONDS ))
}

next_run_ts() {
  [[ -f "$LAST_RUN_FILE" ]] && echo $(( $(cat "$LAST_RUN_FILE") + PERIOD_SECONDS )) || now
}

advance_schedule_and_reset() {
  printf "%s\n" "$(now)" > "$LAST_RUN_FILE"
  ERRORS_IN_ROW=0
  LOGGED_NEXT_RUN=0
}

# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

trim() { printf '%s' "$1" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'; }

extract_meta() {
  local title desc
  title="$(sed -n 's/^TITLE:[[:space:]]*//p' "$1" | head -n 1)"
  desc="$(sed -n 's/^DESC:[[:space:]]*//p'  "$1" | head -n 1)"
  title="$(trim "$title")"
  desc="$(trim "$desc")"
  [[ -n "${title// }" ]] || return 1
  printf '%s\n%s' "$title" "$desc"
}

upload_one() {
  local dir="$1"

  [[ -f "$dir/video_id.txt" ]] && return 100
  [[ -s "$dir/short.mp4"   ]] || return 100
  [[ -s "$dir/meta_raw.txt" ]] || { echo "[skip] $dir: meta_raw.txt missing/empty" >&2; return 100; }

  local title desc video_id word
  mapfile -t lines < <(extract_meta "$dir/meta_raw.txt" || true)
  [[ ${#lines[@]} -ge 1 ]] || { echo "[skip] $dir: bad meta (no TITLE)" >&2; return 100; }
  title="${lines[0]}"
  desc="${lines[1]:-}"

  echo "[upload] $dir -> $title" >&2
  video_id="$(upload.py -t "$title" -d "$desc" -p "public" "$dir/short.mp4" | tr -d '\r\n')"
  [[ -n "${video_id// }" ]] || { echo "ERROR: empty video_id from upload.py ($dir)" >&2; return 1; }

  printf '%s' "$video_id" > "$dir/video_id.txt"
  echo "[ok] $dir -> $video_id" >&2

  word=""
  [[ -s "$dir/word.txt" ]] && word="$(tr -d '\r\n' < "$dir/word.txt")"
  send-telegram.sh "$(printf '%s\n%s\n%s' "${word:+$word:}" "$title" "https://www.youtube.com/shorts/$video_id")" || true
}

# rc: 0 = uploaded, 100 = nothing to upload, else = error
upload_missing() {
  [[ "${TEST:-0}" == "1" ]] && { echo "test error" >&2; exit 4; }

  shopt -s nullglob
  local dirs=( "$WORKSPACE"/20??????-* ) d rc

  [[ ${#dirs[@]} -gt 0 ]] || { echo "[info] No run dirs in $WORKSPACE" >&2; return 100; }

  for d in "${dirs[@]}"; do
    [[ -d "$d" ]] || continue
    set +e; upload_one "$d"; rc=$?; set -e
    (( rc == 0   )) && return 0
    (( rc == 100 )) && continue
    return "$rc"
  done
  return 100
}

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

run_if_due() {
  if ! should_run; then
    if (( LOGGED_NEXT_RUN == 0 )); then
      echo "[entrypoint] Will run at $(date -d "@$(next_run_ts)" -Is)" >&2
      LOGGED_NEXT_RUN=1
    fi
    return 0
  fi

  echo "[entrypoint] Running upload_missing" >&2
  local tmp rc
  tmp="$(mktemp)"

  set +e
  upload_missing 2>&1 | tee /dev/stderr >"$tmp"
  rc=${PIPESTATUS[0]}
  set -e

  if grep -Fq "test error" "$tmp"; then
    send-telegram.sh "🧪 test error: advancing schedule at $(date -Is)" || true
    advance_schedule_and_reset
    rm -f "$tmp"; return 0
  fi

  if (( rc == 0 || rc == 100 )); then
    [[ $rc == 0 ]] && echo "[entrypoint] Uploaded successfully" >&2 \
                   || echo "[entrypoint] Nothing to upload (rc=100)" >&2
    advance_schedule_and_reset
    rm -f "$tmp"; return 0
  fi

  ERRORS_IN_ROW=$(( ERRORS_IN_ROW + 1 ))
  echo "[entrypoint] Failed (rc=$rc), errors_in_row=$ERRORS_IN_ROW" >&2
  send-telegram.sh "❌ upload_missing failed (rc=$rc) at $(date -Is)

$(tail -n 50 "$tmp")

Errors in row: $ERRORS_IN_ROW" || true

  if (( ERRORS_IN_ROW >= ERROR_RESET_THRESHOLD )); then
    echo "[entrypoint] Hit threshold ($ERROR_RESET_THRESHOLD), resetting" >&2
    advance_schedule_and_reset
    send-telegram.sh "⚠️ $ERROR_RESET_THRESHOLD consecutive errors — resetting at $(date -Is)" || true
  fi

  rm -f "$tmp"
}

# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------

MOTD="tupinumboor/generator-1/ms2-uploader:$VERSION started"
validate.sh
mkdir -p "$WORKSPACE"
echo "$MOTD"
send-telegram.sh "$MOTD"

while true; do
  run_if_due
  sleep 1
done
