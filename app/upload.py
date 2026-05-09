#!/usr/bin/env python3
import argparse
import os

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

TOKEN_JSON_FILE = ".auth/token.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload a video to YouTube.")
    parser.add_argument("video", help="Path to video file (e.g. file.mp4)")
    parser.add_argument("-t", "--title", required=True, help="Video title")
    parser.add_argument("-d", "--description", default="", help="Video description")
    parser.add_argument(
        "-p",
        "--privacy",
        choices=["public", "unlisted", "private"],
        default="public",
        help="Privacy status",
    )
    args = parser.parse_args()

    if not os.path.exists(TOKEN_JSON_FILE):
        raise FileNotFoundError(f"{TOKEN_JSON_FILE} not found")

    if not os.path.exists(args.video):
        raise FileNotFoundError(f"{args.video} not found")

    creds = Credentials.from_authorized_user_file(TOKEN_JSON_FILE, SCOPES)
    youtube = build("youtube", "v3", credentials=creds)

    request = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": args.title,
                "description": args.description,
            },
            "status": {
                "privacyStatus": args.privacy,
            },
        },
        media_body=MediaFileUpload(args.video, resumable=True),
    )

    response = request.execute()
    print(response["id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
