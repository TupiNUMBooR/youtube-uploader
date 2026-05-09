#!/usr/bin/env python3

from google_auth_oauthlib.flow import InstalledAppFlow

flow = InstalledAppFlow.from_client_secrets_file(
    ".auth/client_secret.json",
    [
        "https://www.googleapis.com/auth/youtube.upload",
        # "https://www.googleapis.com/auth/youtube.force-ssl"
    ]
)

creds = flow.run_local_server(port=0)
json = creds.to_json()

with open(".auth/token.json", "w") as f:
    f.write(json)

print("Created .auth/token.json")
