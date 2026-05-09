#!/usr/bin/env python3
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

AUTH_DIR = Path(".auth")
CLIENT_SECRET_FILE = AUTH_DIR / "client_secret.json"
TOKEN_FILE = AUTH_DIR / "token.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

AUTH_DIR.mkdir(parents=True, exist_ok=True)
flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_FILE), SCOPES)
creds = flow.run_local_server(port=0)
TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
print(f"Created {TOKEN_FILE}")
