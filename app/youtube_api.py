from __future__ import annotations

from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from logger import Logger
from models import VideoUploadRequest, VideoUploadResult

TOKEN_FILE = Path("/.auth/token.json")
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def validate_token(logger: Logger) -> None:
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


def make_video_body(request: VideoUploadRequest) -> dict[str, Any]:
    status: dict[str, Any] = {"privacyStatus": request.privacy}

    if request.publish_at:
        status["privacyStatus"] = "private"
        status["publishAt"] = request.publish_at_iso

    return {
        "snippet": {
            "title": request.title,
            "description": request.description,
        },
        "status": status,
    }


def upload_video(request: VideoUploadRequest, logger: Logger) -> VideoUploadResult:
    youtube = build_youtube()
    body = make_video_body(request)
    status = body["status"]

    logger.write(
        f"uploading video: {request.video_file.name}; "
        f"title={request.title!r}; "
        f"privacy={status['privacyStatus']}"
    )

    response = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload(str(request.video_file), resumable=True),
    ).execute()

    video_id = response["id"]
    url = f"https://youtu.be/{video_id}"
    logger.write(
        f"video uploaded: {url}; "
        f"title={request.title!r}; "
        f"privacy={status['privacyStatus']}"
    )

    if request.thumbnail_file:
        try:
            logger.write(f"setting thumbnail: {request.thumbnail_file.name}")
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(str(request.thumbnail_file)),
            ).execute()
            logger.write("thumbnail set")
        except Exception as exc:
            logger.write(f"thumbnail failed, video stays uploaded: {type(exc).__name__}: {exc}")

    return VideoUploadResult(video_id=video_id, url=url)
