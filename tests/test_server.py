from __future__ import annotations

import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from youtube_uploader import server
from youtube_uploader.youtube_api import ChannelToken, VideoUploadResult

client = TestClient(server.app)


def test_get_channel_returns_200() -> None:
    token = ChannelToken(handle="@test", path=server.Path("/tmp/token.@test.json"))
    with patch.object(server, "token_for_channel", return_value=token):
        response = client.get("/channels/@test")

    assert response.status_code == 200
    assert response.json() == {"handle": "@test"}


def test_get_channel_returns_404() -> None:
    with patch.object(server, "token_for_channel", side_effect=FileNotFoundError()):
        response = client.get("/channels/@missing")

    assert response.status_code == 404
    assert response.json()["error"] == "channel_not_found"


def test_post_upload_accepts_optional_thumbnail() -> None:
    metadata = {
        "channel": "@test",
        "title": "Test title",
        "description": "Test description",
        "privacy": "unlisted",
    }

    with (
        patch.object(server, "token_for_channel"),
        patch.object(
            server,
            "upload_video",
            return_value=VideoUploadResult(
                "abc123",
                "https://youtu.be/abc123",
                "https://www.youtube.com/shorts/abc123",
            ),
        ) as upload_mock,
    ):
        response = client.post(
            "/uploads",
            data={"metadata": json.dumps(metadata)},
            files={"video": ("some-video.mp4", b"video", "video/mp4")},
        )

    assert response.status_code == 200
    assert response.json()["shorts_url"] == "https://www.youtube.com/shorts/abc123"
    request = upload_mock.call_args.args[1]
    assert request.title == "Test title"
    assert request.thumbnail_file is None


def test_post_upload_rejects_unknown_channel_before_saving_video() -> None:
    metadata = {"channel": "@missing", "privacy": "private"}

    with (
        patch.object(server, "token_for_channel", side_effect=FileNotFoundError()),
        patch.object(server, "save_upload") as save_mock,
    ):
        response = client.post(
            "/uploads",
            data={"metadata": json.dumps(metadata)},
            files={"video": ("video.mp4", b"video", "video/mp4")},
        )

    assert response.status_code == 404
    save_mock.assert_not_called()


def test_post_upload_rejects_video_over_size_limit(monkeypatch) -> None:
    metadata = {"channel": "@test", "privacy": "private"}
    monkeypatch.setattr(server, "MAX_VIDEO_BYTES", 4)

    with patch.object(server, "token_for_channel"):
        response = client.post(
            "/uploads",
            data={"metadata": json.dumps(metadata)},
            files={"video": ("video.mp4", b"video", "video/mp4")},
        )

    assert response.status_code == 413
    assert response.json() == {
        "error": "file_too_large",
        "message": "file exceeds 4 bytes",
    }
