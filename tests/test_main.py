from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import main
from jobs import UploadJob
from youtube_api import VideoUploadResult


def make_job(tmp_path: Path) -> UploadJob:
    job_dir = tmp_path / "job-1"
    job_dir.mkdir()

    video_file = job_dir / "video.mp4"
    video_file.write_bytes(b"fake video")

    return UploadJob(
        directory=job_dir,
        meta={
            "title": "Test title",
            "description": "Test description",
            "privacy": "unlisted",
        },
        video_file=video_file,
        thumbnail_file=None,
    )


def test_upload_job_success(tmp_path: Path) -> None:
    job = make_job(tmp_path)

    with patch.object(main, "upload_video", return_value=VideoUploadResult("abc123", "https://youtu.be/abc123")) as upload_mock:
        result = main.upload_job(job)

    assert result.video_id == "abc123"
    assert result.url == "https://youtu.be/abc123"

    upload_mock.assert_called_once()

    content = (job.directory / main.LOG_FILE).read_text(encoding="utf-8")
    assert "upload started" in content
    assert "upload complete: https://youtu.be/abc123" in content


def test_upload_job_failure_bubbles_up(tmp_path: Path) -> None:
    job = make_job(tmp_path)

    with patch.object(main, "upload_video", side_effect=RuntimeError("boom")):
        try:
            main.upload_job(job)
        except RuntimeError as exc:
            assert str(exc) == "boom"
        else:
            raise AssertionError("upload_job should bubble up upload errors")


def test_request_stop_sets_stop_event() -> None:
    main.stop_event.clear()

    main.request_stop(None, None)

    assert main.stop_event.is_set()

    main.stop_event.clear()


def test_parse_job_dir_defaults_to_job() -> None:
    assert main.parse_job_dir() == Path("/job")
    assert main.parse_job_dir(["/tmp/job"]) == Path("/tmp/job")


def test_main_uploads_one_job(tmp_path: Path) -> None:
    job = make_job(tmp_path)

    with (
        patch.object(main.signal, "signal"),
        patch.object(main, "validate_token") as validate_token_mock,
        patch.object(main, "load_job", return_value=job) as load_job_mock,
        patch.object(main, "upload_job", return_value=VideoUploadResult("abc123", "https://youtu.be/abc123")) as upload_job_mock,
    ):
        result = main.main([str(job.directory)])

    assert result == 0

    validate_token_mock.assert_called_once()
    load_job_mock.assert_called_once_with(job.directory)
    upload_job_mock.assert_called_once_with(job)


def test_main_returns_failure_code(tmp_path: Path) -> None:
    with (
        patch.object(main.signal, "signal"),
        patch.object(main, "validate_token"),
        patch.object(main, "load_job", side_effect=RuntimeError("boom")),
    ):
        result = main.main([str(tmp_path / "job")])

    assert result == 1
