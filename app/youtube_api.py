from __future__ import annotations

from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

TOKEN_FILE = Path("/.auth/token.json")
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def validate_token(logger: Any) -> None:
    if not TOKEN_FILE.is_file():
        raise FileNotFoundError(f"token not found: {TOKEN_FILE}")

    creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if creds.expired or not creds.valid:
        logger.write("OAuth token expired or invalid; refreshing")
        creds.refresh(Request())
        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
        logger.write("OAuth token refreshed")
        return

    logger.write("OAuth token looks valid")


def build_youtube() -> Any:
    creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    return build("youtube", "v3", credentials=creds)


def upload_video(job: Any, logger: Any) -> tuple[str, str]:
    youtube = build_youtube()

    status: dict[str, Any] = {"privacyStatus": job.privacy}
    if job.publish_at:
        status["privacyStatus"] = "private"
        status["publishAt"] = job.publish_at_iso

    body = {
        "snippet": {
            "title": job.title,
            "description": job.description,
        },
        "status": status,
    }

    logger.write(
        f"uploading video: {job.video_file.name}; "
        f"title={job.title!r}; "
        f"privacy={status['privacyStatus']}"
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload(str(job.video_file), resumable=True),
    )

    response = request.execute()
    video_id = response["id"]
    url = f"https://youtu.be/{video_id}"

    logger.write(f"video uploaded: {url}")

    if job.thumbnail_file:
        logger.write(f"setting thumbnail: {job.thumbnail_file.name}")
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(str(job.thumbnail_file)),
        ).execute()
        logger.write("thumbnail set")

    return video_id, url
