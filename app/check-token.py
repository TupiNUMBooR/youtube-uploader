#!/usr/bin/env python3
"""
check-token.py — validate YouTube OAuth2 token freshness.

Exit codes:
  0  token is valid and not expiring soon
  1  token is missing, invalid, or cannot be refreshed
  2  token was refreshed successfully (still usable)
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_JSON_FILE = os.path.join(SCRIPTS_DIR, "..", ".auth", "token.json")
TOKEN_JSON_FILE = os.path.normpath(TOKEN_JSON_FILE)

# Warn if token expires within this window
EXPIRY_WARN_SECONDS = int(os.environ.get("TOKEN_EXPIRY_WARN_SECONDS", "300"))


def fail(msg: str) -> None:
    print(f"  [FAIL] {msg}", file=sys.stderr)
    sys.exit(1)


def warn(msg: str) -> None:
    print(f"  [WARN] {msg}", file=sys.stderr)


def ok(msg: str) -> None:
    print(f"  [OK]   {msg}")


def check_token() -> None:
    # 1. File existence
    if not os.path.isfile(TOKEN_JSON_FILE):
        fail(f"token.json not found: {TOKEN_JSON_FILE}")

    # 2. JSON parse
    try:
        with open(TOKEN_JSON_FILE, "r") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        fail(f"token.json is not valid JSON: {e}")
        return  # unreachable, satisfies type checker

    ok(f"token.json found: {TOKEN_JSON_FILE}")

    # 3. Required fields
    for field in ("token", "refresh_token", "client_id", "client_secret", "token_uri"):
        if not data.get(field):
            fail(f"token.json missing required field: '{field}'")

    ok("token.json has all required fields")

    # 4. Expiry check
    expiry_str: str | None = data.get("expiry")
    if not expiry_str:
        warn("token.json has no 'expiry' field — cannot check freshness")
    else:
        # Google stores expiry as ISO-8601, e.g. "2026-03-01T12:00:00.000000Z"
        try:
            expiry_str_clean = expiry_str.replace("Z", "+00:00")
            expiry = datetime.fromisoformat(expiry_str_clean)
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
        except ValueError as e:
            fail(f"token.json 'expiry' is not a valid datetime: {e}")
            return

        now = datetime.now(tz=timezone.utc)
        remaining = expiry - now

        if remaining.total_seconds() <= 0:
            warn(f"Access token EXPIRED at {expiry.isoformat()} — will rely on refresh_token")
        elif remaining.total_seconds() <= EXPIRY_WARN_SECONDS:
            warn(
                f"Access token expires in {int(remaining.total_seconds())}s "
                f"(threshold: {EXPIRY_WARN_SECONDS}s) — will need refresh soon"
            )
        else:
            ok(f"Access token valid for {int(remaining.total_seconds())}s (expires {expiry.isoformat()})")

    # 5. Try a live refresh to confirm refresh_token works
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
    except ImportError:
        warn("google-auth not installed — skipping live token refresh check")
        return

    creds = Credentials(
        token=data.get("token"),
        refresh_token=data.get("refresh_token"),
        token_uri=data.get("token_uri"),
        client_id=data.get("client_id"),
        client_secret=data.get("client_secret"),
        scopes=data.get("scopes"),
    )

    if creds.expired or not creds.valid:
        try:
            creds.refresh(Request())
            # Persist refreshed token
            token_data = {
                "token": creds.token,
                "refresh_token": creds.refresh_token,
                "token_uri": creds.token_uri,
                "client_id": creds.client_id,
                "client_secret": creds.client_secret,
                "scopes": list(creds.scopes) if creds.scopes else data.get("scopes"),
                "expiry": creds.expiry.isoformat() if creds.expiry else None,
            }
            with open(TOKEN_JSON_FILE, "w") as f:
                json.dump(token_data, f, indent=2)
            ok("Token refreshed and saved successfully")
            sys.exit(2)
        except Exception as e:
            fail(f"Token refresh FAILED: {e}")
    else:
        ok("Token is valid (no refresh needed)")


if __name__ == "__main__":
    check_token()
