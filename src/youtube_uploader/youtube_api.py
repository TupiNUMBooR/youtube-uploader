from __future__ import annotations

import json
import os
import random
import re
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import httplib2
from google.auth.exceptions import TransportError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from filelock import FileLock

from youtube_uploader.logger import log, warn
from youtube_uploader.time_utils import iso_utc

AUTH_DIR = Path("/.auth")
TOKEN_PATTERN = re.compile(r"^token\.(@[A-Za-z0-9._-]+)\.json$")
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]

MAX_UPLOAD_ATTEMPTS = int(os.environ.get("MAX_UPLOAD_ATTEMPTS", "5"))
RETRY_BASE_SECONDS = float(os.environ.get("RETRY_BASE_SECONDS", "1"))
RETRY_MAX_SECONDS = float(os.environ.get("RETRY_MAX_SECONDS", "30"))
RETRYABLE_HTTP_STATUSES = {429, 500, 502, 503, 504}


class TokenError(RuntimeError):
    pass


@dataclass(frozen=True)
class ChannelToken:
    handle: str
    path: Path


@dataclass(frozen=True)
class VideoUploadRequest:
    video_file: Path
    thumbnail_file: Path | None
    title: str
    description: str
    privacy: str
    publish_at: datetime | None
    default_language: str | None = None
    localizations: dict[str, dict[str, str]] | None = None

    @property
    def publish_at_iso(self) -> str | None:
        return iso_utc(self.publish_at) if self.publish_at else None


@dataclass(frozen=True)
class VideoUploadResult:
    video_id: str
    url: str
    shorts_url: str


def _load_credentials(path: Path) -> Credentials:
    try:
        creds = Credentials.from_authorized_user_file(str(path), SCOPES)
    except Exception as exc:
        raise TokenError(f"invalid token file {path}: {type(exc).__name__}: {exc}") from exc

    missing = [
        name
        for name, value in (
            ("refresh_token", creds.refresh_token),
            ("client_id", creds.client_id),
            ("client_secret", creds.client_secret),
            ("token_uri", creds.token_uri),
        )
        if not value
    ]
    if missing:
        raise TokenError(f"invalid token file {path}: missing {', '.join(missing)}")
    if not creds.has_scopes(SCOPES):
        raise TokenError(f"invalid token file {path}: required YouTube scopes are missing")
    return creds


def discover_tokens(auth_dir: Path | None = None) -> dict[str, ChannelToken]:
    auth_dir = auth_dir or AUTH_DIR
    tokens: dict[str, ChannelToken] = {}

    for path in sorted(auth_dir.glob("token.*.json")):
        match = TOKEN_PATTERN.fullmatch(path.name)
        if not match:
            raise TokenError(f"invalid token filename: {path.name}")

        handle = match.group(1)
        _load_credentials(path)
        tokens[handle] = ChannelToken(handle=handle, path=path)

    if not tokens:
        raise TokenError(f"no token.*.json files found in {auth_dir}")

    return tokens


def token_for_channel(handle: str, auth_dir: Path | None = None) -> ChannelToken:
    if not re.fullmatch(r"@[A-Za-z0-9._-]+", handle):
        raise TokenError(f"invalid channel handle: {handle!r}")

    token = discover_tokens(auth_dir).get(handle)
    if token is None:
        raise FileNotFoundError(f"channel token not found: {handle}")
    return token


def _write_credentials_atomically(path: Path, creds: Credentials) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f"{path.name}.", suffix=".tmp", dir=path.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(creds.to_json())
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, path)
    finally:
        tmp_path.unlink(missing_ok=True)


def load_credentials_for_channel(handle: str) -> Credentials:
    token = token_for_channel(handle)
    lock_dir = token.path.parent / ".locks"
    lock_dir.mkdir(mode=0o700, exist_ok=True)
    lock_path = lock_dir / f"{token.path.name}.lock"

    with FileLock(lock_path):
        creds = _load_credentials(token.path)

        if not creds.valid:
            log(f"OAuth token refresh channel={handle}")
            creds.refresh(Request())
            _write_credentials_atomically(token.path, creds)
            log(f"OAuth token refreshed channel={handle}")

    return creds


def build_youtube(handle: str) -> Any:
    creds = load_credentials_for_channel(handle)
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def make_video_body(request: VideoUploadRequest) -> dict[str, Any]:
    status: dict[str, Any] = {"privacyStatus": request.privacy}

    if request.publish_at:
        status["privacyStatus"] = "private"
        status["publishAt"] = request.publish_at_iso

    snippet: dict[str, Any] = {
        "title": request.title,
        "description": request.description,
    }
    if request.default_language:
        snippet["defaultLanguage"] = request.default_language

    body: dict[str, Any] = {
        "snippet": snippet,
        "status": status,
    }
    if request.localizations:
        body["localizations"] = request.localizations
    return body


def _http_status(exc: HttpError) -> int:
    return int(getattr(exc.resp, "status", 0) or 0)


def youtube_error_reason(exc: HttpError) -> str | None:
    try:
        payload = json.loads(exc.content.decode("utf-8", errors="replace"))
        return payload["error"]["errors"][0].get("reason")
    except (KeyError, IndexError, TypeError, ValueError, AttributeError):
        return None


def _retry_delay(attempt: int) -> float:
    ceiling = min(RETRY_MAX_SECONDS, RETRY_BASE_SECONDS * (2 ** (attempt - 1)))
    return random.uniform(0, ceiling)


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, HttpError):
        return _http_status(exc) in RETRYABLE_HTTP_STATUSES
    return isinstance(exc, (TransportError, httplib2.HttpLib2Error, OSError, TimeoutError))


def _set_thumbnail_with_retries(call: Callable[[], Any]) -> bool:
    attempts = 3
    for attempt in range(1, attempts + 1):
        try:
            call()
            return True
        except Exception as exc:
            warn(
                f"thumbnail failed attempt={attempt}/{attempts}: "
                f"{type(exc).__name__}: {exc}"
            )
            if attempt < attempts:
                time.sleep(_retry_delay(attempt))
    return False


def _execute_resumable(request: Any) -> dict[str, Any]:
    response: dict[str, Any] | None = None
    attempt = 0

    while response is None:
        try:
            _, response = request.next_chunk()
            attempt = 0
        except Exception as exc:
            attempt += 1
            if not _is_retryable(exc) or attempt >= MAX_UPLOAD_ATTEMPTS:
                raise
            delay = _retry_delay(attempt)
            warn(
                f"video upload retry={attempt}/{MAX_UPLOAD_ATTEMPTS} "
                f"reason={type(exc).__name__} delay={delay:.1f}s"
            )
            time.sleep(delay)

    return response


def upload_video(handle: str, request: VideoUploadRequest) -> VideoUploadResult:
    youtube = build_youtube(handle)
    body = make_video_body(request)
    status = body["status"]

    log(
        f"upload video channel={handle} file={request.video_file.name} "
        f"title={request.title!r} privacy={status['privacyStatus']}"
    )

    insert = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload(str(request.video_file), resumable=True),
    )
    response = _execute_resumable(insert)

    video_id = response["id"]
    url = f"https://youtu.be/{video_id}"
    shorts_url = f"https://www.youtube.com/shorts/{video_id}"
    log(f"video uploaded channel={handle} video_id={video_id} url={url}")

    if request.thumbnail_file:
        log(f"set thumbnail channel={handle} file={request.thumbnail_file.name}")
        thumbnail_request = youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(str(request.thumbnail_file)),
        )
        if _set_thumbnail_with_retries(thumbnail_request.execute):
            log(f"thumbnail set channel={handle} video_id={video_id}")

    return VideoUploadResult(video_id=video_id, url=url, shorts_url=shorts_url)
