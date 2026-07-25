#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

AUTH_DIR = Path("/.auth")
CLIENT_SECRET_FILE = AUTH_DIR / "client_secret.json"
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]
PORT = int(os.environ.get("PORT", "8080"))
HANDLE_PATTERN = re.compile(r"^@[A-Za-z0-9._-]+$")


def save_token(path: Path, content: str) -> None:
    fd, tmp_name = tempfile.mkstemp(prefix=f"{path.name}.", suffix=".tmp", dir=path.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, path)
    finally:
        tmp_path.unlink(missing_ok=True)


def detect_channel(creds) -> tuple[str, str, str]:
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    response = youtube.channels().list(part="id,snippet", mine=True).execute()
    items = response.get("items", [])
    if len(items) != 1:
        raise RuntimeError(f"expected exactly one authorized YouTube channel, got {len(items)}")

    channel = items[0]
    snippet = channel.get("snippet", {})
    handle = str(snippet.get("customUrl", "")).strip()
    if not HANDLE_PATTERN.fullmatch(handle):
        raise RuntimeError(f"YouTube channel handle is missing or invalid: {handle!r}")

    return handle, str(channel["id"]), str(snippet.get("title", ""))


def create_token() -> Path:
    AUTH_DIR.mkdir(parents=True, exist_ok=True)

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_FILE), SCOPES)
    creds = flow.run_local_server(
        host="localhost",
        bind_addr="0.0.0.0",
        port=PORT,
        open_browser=False,
    )

    handle, channel_id, title = detect_channel(creds)
    token_file = AUTH_DIR / f"token.{handle}.json"
    save_token(token_file, creds.to_json())

    print(f"Created {token_file}")
    print(f"Channel: {handle} ({channel_id}) {title}")
    return token_file


if __name__ == "__main__":
    create_token()
