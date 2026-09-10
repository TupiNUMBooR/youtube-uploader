from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from youtube_uploader import youtube_api
from youtube_uploader.time_utils import parse_iso_utc
from youtube_uploader.youtube_api import VideoUploadRequest


def token_payload() -> dict[str, object]:
    return {
        "token": "access",
        "refresh_token": "refresh",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "client",
        "client_secret": "secret",
        "scopes": youtube_api.SCOPES,
        "expiry": "2099-01-01T00:00:00Z",
    }


def write_token(auth_dir: Path, handle: str = "@test") -> Path:
    auth_dir.mkdir(parents=True, exist_ok=True)
    path = auth_dir / f"token.{handle}.json"
    path.write_text(json.dumps(token_payload()), encoding="utf-8")
    return path


def make_request(tmp_path: Path, thumbnail: bool = False) -> VideoUploadRequest:
    video_file = tmp_path / "video.mp4"
    video_file.write_bytes(b"fake video")

    thumbnail_file = None
    if thumbnail:
        thumbnail_file = tmp_path / "thumb.jpg"
        thumbnail_file.write_bytes(b"fake thumbnail")

    return VideoUploadRequest(
        video_file=video_file,
        thumbnail_file=thumbnail_file,
        title="Test title",
        description="Test description",
        privacy="unlisted",
        publish_at=None,
    )


def test_discover_tokens(tmp_path: Path) -> None:
    write_token(tmp_path, "@first")
    write_token(tmp_path, "@second")

    tokens = youtube_api.discover_tokens(tmp_path)

    assert set(tokens) == {"@first", "@second"}


def test_discover_tokens_requires_at_least_one(tmp_path: Path) -> None:
    try:
        youtube_api.discover_tokens(tmp_path)
    except youtube_api.TokenError as exc:
        assert "no token.*.json" in str(exc)
    else:
        raise AssertionError("discover_tokens should reject an empty directory")


def test_credentials_lock_is_stored_in_hidden_directory(tmp_path: Path) -> None:
    token_path = write_token(tmp_path)

    with (
        patch.object(
            youtube_api,
            "token_for_channel",
            return_value=youtube_api.ChannelToken(handle="@test", path=token_path),
        ),
        patch.object(youtube_api, "FileLock", wraps=youtube_api.FileLock) as file_lock_mock,
    ):
        youtube_api.load_credentials_for_channel("@test")

    file_lock_mock.assert_called_once_with(tmp_path / ".locks" / "token.@test.json.lock")
    assert (tmp_path / ".locks").is_dir()
    assert not (tmp_path / "token.@test.json.lock").exists()


def test_make_video_body_without_publish_at(tmp_path: Path) -> None:
    request = make_request(tmp_path)
    assert youtube_api.make_video_body(request) == {
        "snippet": {"title": "Test title", "description": "Test description"},
        "status": {"privacyStatus": "unlisted"},
    }


def test_make_video_body_with_publish_at(tmp_path: Path) -> None:
    request = VideoUploadRequest(
        video_file=tmp_path / "video.mp4",
        thumbnail_file=None,
        title="Scheduled title",
        description="Scheduled description",
        privacy="unlisted",
        publish_at=parse_iso_utc("2026-05-09T12:00:00Z"),
    )
    assert youtube_api.make_video_body(request)["status"] == {
        "privacyStatus": "private",
        "publishAt": "2026-05-09T12:00:00Z",
    }


def test_make_video_body_with_localizations(tmp_path: Path) -> None:
    request = make_request(tmp_path)
    request = VideoUploadRequest(
        video_file=request.video_file,
        thumbnail_file=request.thumbnail_file,
        title=request.title,
        description=request.description,
        privacy=request.privacy,
        publish_at=request.publish_at,
        default_language="en",
        localizations={
            "en": {"title": "Test title", "description": "English"},
            "ru": {"title": "Тест", "description": "Русский"},
        },
    )

    body = youtube_api.make_video_body(request)

    assert body["snippet"]["defaultLanguage"] == "en"
    assert body["localizations"]["ru"]["title"] == "Тест"


def test_upload_video_returns_both_urls(tmp_path: Path) -> None:
    request = make_request(tmp_path)
    youtube = MagicMock()
    insert = youtube.videos.return_value.insert.return_value
    insert.next_chunk.return_value = (None, {"id": "abc123"})

    with (
        patch.object(youtube_api, "build_youtube", return_value=youtube),
        patch.object(youtube_api, "MediaFileUpload") as media_upload_mock,
    ):
        result = youtube_api.upload_video("@test", request)

    assert result.video_id == "abc123"
    assert result.url == "https://youtu.be/abc123"
    assert result.shorts_url == "https://www.youtube.com/shorts/abc123"
    media_upload_mock.assert_called_once_with(str(request.video_file), resumable=True)


def test_upload_video_sets_optional_thumbnail(tmp_path: Path) -> None:
    request = make_request(tmp_path, thumbnail=True)
    youtube = MagicMock()
    youtube.videos.return_value.insert.return_value.next_chunk.return_value = (None, {"id": "abc123"})

    with (
        patch.object(youtube_api, "build_youtube", return_value=youtube),
        patch.object(youtube_api, "MediaFileUpload"),
    ):
        youtube_api.upload_video("@test", request)

    youtube.thumbnails.return_value.set.assert_called_once()
    youtube.thumbnails.return_value.set.return_value.execute.assert_called_once()


def test_thumbnail_failure_warns_three_times_and_keeps_video_uploaded(tmp_path: Path) -> None:
    request = make_request(tmp_path, thumbnail=True)
    youtube = MagicMock()
    youtube.videos.return_value.insert.return_value.next_chunk.return_value = (None, {"id": "abc123"})
    thumbnail_execute = youtube.thumbnails.return_value.set.return_value.execute
    thumbnail_execute.side_effect = RuntimeError("thumbnail unavailable")

    with (
        patch.object(youtube_api, "build_youtube", return_value=youtube),
        patch.object(youtube_api, "MediaFileUpload"),
        patch.object(youtube_api, "warn") as warn_mock,
        patch.object(youtube_api.time, "sleep"),
    ):
        result = youtube_api.upload_video("@test", request)

    assert result.video_id == "abc123"
    assert thumbnail_execute.call_count == 3
    assert warn_mock.call_count == 3
    assert [call.args[0] for call in warn_mock.call_args_list] == [
        "thumbnail failed attempt=1/3: RuntimeError: thumbnail unavailable",
        "thumbnail failed attempt=2/3: RuntimeError: thumbnail unavailable",
        "thumbnail failed attempt=3/3: RuntimeError: thumbnail unavailable",
    ]
