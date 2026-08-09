from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse
import httplib2
from google.auth.exceptions import RefreshError, TransportError
from googleapiclient.errors import HttpError
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from logger import error, log
from time_utils import parse_iso_utc
from youtube_api import (
    TokenError,
    VideoUploadRequest,
    discover_tokens,
    token_for_channel,
    upload_video,
    youtube_error_reason,
)

THUMBNAIL_MAX_BYTES = 2_097_152
MAX_VIDEO_BYTES = int(os.environ.get("MAX_VIDEO_BYTES", "10737418240"))
PRIVACY_VALUES = {"private", "unlisted", "public"}

app = FastAPI(title="youtube-uploader", docs_url=None, redoc_url=None)


class UploadMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel: str
    title: str | None = None
    description: str = ""
    privacy: str
    publish_at: str | None = None

    @field_validator("channel")
    @classmethod
    def validate_channel(cls, value: str) -> str:
        value = value.strip()
        if not value.startswith("@"):
            raise ValueError("channel must be a YouTube handle starting with @")
        return value

    @field_validator("privacy")
    @classmethod
    def validate_privacy(cls, value: str) -> str:
        value = value.strip()
        if value not in PRIVACY_VALUES:
            raise ValueError("privacy must be private, unlisted, or public")
        return value

    @field_validator("publish_at")
    @classmethod
    def validate_publish_at(cls, value: str | None) -> str | None:
        if value is not None and value.strip():
            parse_iso_utc(value)
            return value.strip()
        return None


def api_error(status: int, code: str, message: str, **extra: Any) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": code, "message": message, **extra},
    )


def save_upload(source: UploadFile, destination: Path, max_bytes: int | None = None) -> int:
    total = 0
    with destination.open("wb") as output:
        while chunk := source.file.read(1024 * 1024):
            total += len(chunk)
            if max_bytes is not None and total > max_bytes:
                raise ValueError(f"file exceeds {max_bytes} bytes")
            output.write(chunk)
    return total


@app.get("/channels/{handle}")
def get_channel(handle: str):
    try:
        token = token_for_channel(handle)
    except FileNotFoundError:
        return api_error(404, "channel_not_found", f"Channel not found: {handle}")
    except TokenError as exc:
        return api_error(400, "invalid_channel", str(exc))

    return {"handle": token.handle}


@app.post("/uploads")
def create_upload(
    metadata: str = Form(...),
    video: UploadFile = File(...),
    thumbnail: UploadFile | None = File(None),
):
    try:
        parsed = UploadMetadata.model_validate(json.loads(metadata))
    except json.JSONDecodeError as exc:
        return api_error(400, "invalid_metadata_json", str(exc))
    except ValidationError as exc:
        return api_error(422, "invalid_metadata", "Metadata validation failed", details=json.loads(exc.json()))

    try:
        token_for_channel(parsed.channel)
    except FileNotFoundError:
        return api_error(404, "channel_not_found", f"Channel not found: {parsed.channel}")
    except TokenError as exc:
        return api_error(400, "invalid_channel", str(exc))

    suffix = Path(video.filename or "video.mp4").suffix or ".mp4"

    try:
        with tempfile.TemporaryDirectory(prefix="youtube-uploader-") as temp_dir_raw:
            temp_dir = Path(temp_dir_raw)
            video_path = temp_dir / f"video{suffix}"
            video_bytes = save_upload(video, video_path, MAX_VIDEO_BYTES)

            thumbnail_path = None
            thumbnail_bytes = 0
            if thumbnail is not None:
                thumbnail_suffix = Path(thumbnail.filename or "thumbnail.jpg").suffix or ".jpg"
                thumbnail_path = temp_dir / f"thumbnail{thumbnail_suffix}"
                thumbnail_bytes = save_upload(thumbnail, thumbnail_path, THUMBNAIL_MAX_BYTES)

            title = (parsed.title or "").strip() or Path(video.filename or "video").stem
            request = VideoUploadRequest(
                video_file=video_path,
                thumbnail_file=thumbnail_path,
                title=title,
                description=parsed.description.strip(),
                privacy=parsed.privacy,
                publish_at=parse_iso_utc(parsed.publish_at) if parsed.publish_at else None,
            )

            log(
                f"POST /uploads channel={parsed.channel} video={video.filename!r} "
                f"video_bytes={video_bytes} thumbnail_bytes={thumbnail_bytes}"
            )
            result = upload_video(parsed.channel, request)

        return {
            "video_id": result.video_id,
            "url": result.url,
            "shorts_url": result.shorts_url,
        }

    except ValueError as exc:
        return api_error(413, "file_too_large", str(exc))
    except RefreshError as exc:
        error(f"OAuth refresh failed channel={parsed.channel}: {exc}")
        return api_error(401, "oauth_refresh_failed", str(exc))
    except (TransportError, httplib2.HttpLib2Error, OSError, TimeoutError) as exc:
        error(f"YouTube unavailable: {type(exc).__name__}: {exc}")
        return api_error(503, "youtube_unavailable", str(exc))
    except HttpError as exc:
        status = int(getattr(exc.resp, "status", 502) or 502)
        reason = youtube_error_reason(exc)
        error(f"YouTube API failed status={status} reason={reason or 'unknown'}")
        return api_error(
            status,
            "youtube_api_error",
            str(exc),
            youtube_status=status,
            youtube_reason=reason,
        )
    except Exception as exc:
        error(f"upload failed: {type(exc).__name__}: {exc}")
        return api_error(500, "internal_error", f"{type(exc).__name__}: {exc}")
