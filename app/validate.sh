#!/usr/bin/env bash
set -euo pipefail

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

OK=0
FAIL=0

pass() { echo "  [OK]  $*"; ((OK++)) || true; }
fail() { echo "  [FAIL] $*" >&2; ((FAIL++)) || true; }

section() { echo; echo "=== $* ==="; }

# ---------------------------------------------------------------------------
# 1. Shell scripts — existence + executable bit
# ---------------------------------------------------------------------------
section "Shell scripts"

SHELL_SCRIPTS=(
  entrypoint.sh
  send-telegram.sh
)

for script in "${SHELL_SCRIPTS[@]}"; do
  path="$SCRIPTS_DIR/$script"
  if [[ ! -f "$path" ]]; then
    fail "Missing script: $script"
  elif [[ ! -x "$path" ]]; then
    fail "Not executable: $script"
  else
    pass "$script exists and is executable"
  fi
done

# ---------------------------------------------------------------------------
# 2. Python scripts — existence + syntax check
# ---------------------------------------------------------------------------
section "Python scripts"

PYTHON_SCRIPTS=(
  upload.py
  check-token.py
)

if ! command -v python3 >/dev/null 2>&1; then
  fail "python3 not found — cannot validate Python scripts"
else
  pass "python3 is available: $(python3 --version 2>&1)"
  for script in "${PYTHON_SCRIPTS[@]}"; do
    path="$SCRIPTS_DIR/$script"
    if [[ ! -f "$path" ]]; then
      fail "Missing Python script: $script"
    elif python3 -m py_compile "$path" 2>/dev/null; then
      pass "$script syntax OK"
    else
      fail "$script has syntax errors:"
      python3 -m py_compile "$path" 2>&1 | sed 's/^/    /' >&2
    fi
  done
fi

# ---------------------------------------------------------------------------
# 3. Required system commands
# ---------------------------------------------------------------------------
section "System commands"

REQUIRED_COMMANDS=(
  bash
  curl
  date
  tr
  sed
  head
  tail
  grep
  rm
  mkdir
  find
  realpath
  mktemp
  python3
  pip3
)

for cmd in "${REQUIRED_COMMANDS[@]}"; do
  if command -v "$cmd" >/dev/null 2>&1; then
    pass "command: $cmd"
  else
    fail "missing command: $cmd"
  fi
done

# ---------------------------------------------------------------------------
# 4. Environment variables
# ---------------------------------------------------------------------------
section "Environment variables"

ENV_VARS=(
  VERSION
  PERIOD_SECONDS
  TELEGRAM_BOT_TOKEN
  TELEGRAM_CHAT_ID
)

for var in "${ENV_VARS[@]}"; do
  if [[ -n "${!var:-}" ]]; then
    pass "env: $var is set"
  else
    fail "env: $var is not set"
  fi
done

# ---------------------------------------------------------------------------
# 5. Python packages from requirements.txt
# ---------------------------------------------------------------------------
section "Python packages"

REQUIREMENTS="$SCRIPTS_DIR/../requirements.txt"

if [[ ! -f "$REQUIREMENTS" ]]; then
  fail "requirements.txt not found at: $REQUIREMENTS"
else
  pass "requirements.txt found"
  if ! command -v python3 >/dev/null 2>&1; then
    fail "python3 unavailable — skipping package checks"
  else
    while IFS= read -r line || [[ -n "$line" ]]; do
      [[ -z "$line" || "$line" =~ ^# ]] && continue
      pkg_name="$(echo "$line" | sed 's/[>=<!;\[].*//' | tr -d '[:space:]')"
      [[ -z "$pkg_name" ]] && continue
      if python3 -c "import importlib.util; exit(0 if importlib.util.find_spec('${pkg_name}') is not None else 1)" 2>/dev/null; then
        pass "python package: $pkg_name"
      else
        if pip3 show "$pkg_name" >/dev/null 2>&1; then
          pass "python package (pip): $pkg_name"
        else
          fail "python package missing: $pkg_name"
        fi
      fi
    done < "$REQUIREMENTS"
  fi
fi

# ---------------------------------------------------------------------------
# 6. OAuth2 token check
# ---------------------------------------------------------------------------
section "OAuth2 token"

CHECK_TOKEN_SCRIPT="$SCRIPTS_DIR/check-token.py"

if [[ ! -f "$CHECK_TOKEN_SCRIPT" ]]; then
  fail "check-token.py not found: $CHECK_TOKEN_SCRIPT"
elif ! command -v python3 >/dev/null 2>&1; then
  fail "python3 unavailable — skipping token check"
else
  set +e
  token_output="$(python3 "$CHECK_TOKEN_SCRIPT" 2>&1)"
  token_exit=$?
  set -e
  echo "$token_output"
  case $token_exit in
    0) ((OK++)) || true ;;
    2) ((OK++)) || true; echo "  [INFO] Token was refreshed during check" ;;
    *) ((FAIL++)) || true ;;
  esac
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
section "Summary"
echo "  Passed : $OK"
echo "  Failed : $FAIL"

if [[ "$FAIL" -gt 0 ]]; then
  echo
  echo "Validation FAILED with $FAIL error(s)." >&2
  exit 1
fi

echo
echo "All checks passed."
