from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import main
from config import Config
from models import UploadJob, UploadState, VideoUploadResult


def make_job(tmp_path: Path, attempts: int = 0) -> UploadJob:
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
        state=UploadState(attempts=attempts, base_priority=10),
    )


def test_process_one_success(tmp_path: Path) -> None:
    job = make_job(tmp_path)
    config = Config()

    with (
        patch.object(main, "upload_video", return_value=VideoUploadResult("abc123", "https://youtu.be/abc123")) as upload_mock,
        patch.object(main, "mark_uploaded") as mark_uploaded_mock,
    ):
        result = main.process_one(job, config)

    assert result is True
    assert job.state.attempts == 1

    upload_mock.assert_called_once()
    mark_uploaded_mock.assert_called_once()

    content = (job.directory / main.LOG_FILE).read_text(encoding="utf-8")
    assert "attempt 1/20 started" in content
    assert "upload job complete" in content


def test_process_one_schedules_retry_on_failure(tmp_path: Path) -> None:
    job = make_job(tmp_path)
    config = Config(max_upload_attempts=3)

    with (
        patch.object(main, "upload_video", side_effect=RuntimeError("boom")),
        patch.object(main, "schedule_retry") as schedule_retry_mock,
        patch.object(main, "mark_failed") as mark_failed_mock,
    ):
        result = main.process_one(job, config)

    assert result is False
    assert job.state.attempts == 1
    assert job.state.last_error == "RuntimeError: boom"

    schedule_retry_mock.assert_called_once()
    mark_failed_mock.assert_not_called()

    content = (job.directory / main.LOG_FILE).read_text(encoding="utf-8")
    assert "attempt 1/3 failed: RuntimeError: boom" in content


def test_process_one_marks_failed_after_last_attempt(tmp_path: Path) -> None:
    job = make_job(tmp_path, attempts=2)
    config = Config(max_upload_attempts=3)

    with (
        patch.object(main, "upload_video", side_effect=RuntimeError("boom")),
        patch.object(main, "schedule_retry") as schedule_retry_mock,
        patch.object(main, "mark_failed") as mark_failed_mock,
    ):
        result = main.process_one(job, config)

    assert result is False
    assert job.state.attempts == 3
    assert job.state.last_error == "RuntimeError: boom"

    mark_failed_mock.assert_called_once()
    schedule_retry_mock.assert_not_called()

    content = (job.directory / main.LOG_FILE).read_text(encoding="utf-8")
    assert "attempt 3/3 failed: RuntimeError: boom" in content


def test_request_stop_sets_stop_event() -> None:
    main.stop_event.clear()

    main.request_stop(None, None)

    assert main.stop_event.is_set()

    main.stop_event.clear()


def test_main_one_empty_loop() -> None:
    class StopAfterOneWait:
        def __init__(self) -> None:
            self.wait_calls = 0

        def is_set(self) -> bool:
            return self.wait_calls > 0

        def wait(self, _seconds: int) -> None:
            self.wait_calls += 1

        def set(self) -> None:
            self.wait_calls = 1

    fake_stop_event = StopAfterOneWait()

    with (
        patch.object(main.signal, "signal"),
        patch.object(main, "stop_event", fake_stop_event),
        patch.object(main, "Config", return_value=Config(poll_seconds=1)),
        patch.object(main, "validate_token") as validate_token_mock,
        patch.object(main, "discover_jobs", return_value=[]) as discover_jobs_mock,
        patch.object(main, "process_one") as process_one_mock,
    ):
        result = main.main()

    assert result == 0

    validate_token_mock.assert_called_once()
    discover_jobs_mock.assert_called_once()
    process_one_mock.assert_not_called()
