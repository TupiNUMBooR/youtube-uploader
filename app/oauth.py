#!/usr/bin/env python3
from pathlib import Path
import os

from google_auth_oauthlib.flow import InstalledAppFlow

AUTH_DIR = Path("/.auth")
CLIENT_SECRET_FILE = AUTH_DIR / "client_secret.json"
TOKEN_FILE = AUTH_DIR / "token.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

PORT = int(os.environ.get("PORT", "8080"))


def create_token():
    AUTH_DIR.mkdir(parents=True, exist_ok=True)

    flow = InstalledAppFlow.from_client_secrets_file(
        str(CLIENT_SECRET_FILE),
        SCOPES,
    )

    creds = flow.run_local_server(
        host="localhost",
        bind_addr="0.0.0.0",
        port=PORT,
        open_browser=False,
    )

    TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")

    print(f"Created {TOKEN_FILE}")


if __name__ == "__main__":
    create_token()
