from __future__ import annotations

from unittest.mock import MagicMock, patch

import youtube_api
from logger import Logger
from time_utils import parse_iso_utc
from youtube_api import VideoUploadRequest


def make_request(tmp_path, thumbnail: bool = False) -> VideoUploadRequest:
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


def test_make_video_body_without_publish_at(tmp_path) -> None:
    request = make_request(tmp_path)

    body = youtube_api.make_video_body(request)

    assert body == {
        "snippet": {
            "title": "Test title",
            "description": "Test description",
        },
        "status": {
            "privacyStatus": "unlisted",
        },
    }


def test_make_video_body_with_publish_at(tmp_path) -> None:
    video_file = tmp_path / "video.mp4"
    video_file.write_bytes(b"fake video")

    request = VideoUploadRequest(
        video_file=video_file,
        thumbnail_file=None,
        title="Scheduled title",
        description="Scheduled description",
        privacy="unlisted",
        publish_at=parse_iso_utc("2026-05-09T12:00:00Z"),
    )

    body = youtube_api.make_video_body(request)

    assert body == {
        "snippet": {
            "title": "Scheduled title",
            "description": "Scheduled description",
        },
        "status": {
            "privacyStatus": "private",
            "publishAt": "2026-05-09T12:00:00Z",
        },
    }


def test_validate_token_missing_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(youtube_api, "TOKEN_FILE", tmp_path / "missing-token.json")

    logger = Logger(tmp_path / "test.log")

    try:
        youtube_api.validate_token(logger)
    except FileNotFoundError as exc:
        assert "token not found" in str(exc)
    else:
        raise AssertionError("validate_token should fail when token file is missing")


def test_upload_video_without_thumbnail(tmp_path) -> None:
    request = make_request(tmp_path)
    logger = Logger(tmp_path / "test.log")

    youtube = MagicMock()
    youtube.videos.return_value.insert.return_value.execute.return_value = {"id": "abc123"}

    with (
        patch.object(youtube_api, "build_youtube", return_value=youtube),
        patch.object(youtube_api, "MediaFileUpload") as media_upload_mock,
    ):
        result = youtube_api.upload_video(request, logger)

    assert result.video_id == "abc123"
    assert result.url == "https://youtu.be/abc123"

    youtube.videos.return_value.insert.assert_called_once()
    youtube.thumbnails.return_value.set.assert_not_called()

    media_upload_mock.assert_called_once_with(str(request.video_file), resumable=True)

    log = (tmp_path / "test.log").read_text(encoding="utf-8")
    assert "uploading video: video.mp4" in log
    assert "title='Test title'" in log
    assert "privacy=unlisted" in log

    assert (
        "video uploaded: https://youtu.be/abc123; "
        "title='Test title'; "
        "privacy=unlisted"
    ) in log


def test_upload_video_with_thumbnail(tmp_path) -> None:
    request = make_request(tmp_path, thumbnail=True)
    logger = Logger(tmp_path / "test.log")

    youtube = MagicMock()
    youtube.videos.return_value.insert.return_value.execute.return_value = {"id": "abc123"}

    with (
        patch.object(youtube_api, "build_youtube", return_value=youtube),
        patch.object(youtube_api, "MediaFileUpload") as media_upload_mock,
    ):
        result = youtube_api.upload_video(request, logger)

    assert result.video_id == "abc123"
    assert result.url == "https://youtu.be/abc123"

    youtube.videos.return_value.insert.assert_called_once()
    youtube.thumbnails.return_value.set.assert_called_once()

    assert media_upload_mock.call_count == 2

    log = (tmp_path / "test.log").read_text(encoding="utf-8")
    assert "setting thumbnail: thumb.jpg" in log
    assert "thumbnail set" in log


def test_upload_video_keeps_result_when_thumbnail_fails(tmp_path) -> None:
    request = make_request(tmp_path, thumbnail=True)
    logger = Logger(tmp_path / "test.log")

    youtube = MagicMock()
    youtube.videos.return_value.insert.return_value.execute.return_value = {"id": "abc123"}
    youtube.thumbnails.return_value.set.return_value.execute.side_effect = RuntimeError("thumbnail boom")

    with (
        patch.object(youtube_api, "build_youtube", return_value=youtube),
        patch.object(youtube_api, "MediaFileUpload"),
    ):
        result = youtube_api.upload_video(request, logger)

    assert result.video_id == "abc123"
    assert result.url == "https://youtu.be/abc123"

    log = (tmp_path / "test.log").read_text(encoding="utf-8")
    assert "thumbnail failed, video stays uploaded" in log
    assert "RuntimeError: thumbnail boom" in log
