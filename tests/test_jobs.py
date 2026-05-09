from __future__ import annotations

from pathlib import Path

import jobs
from config import Config
from jobs import (
    FAILED_FILE,
    META_FILE,
    UPLOADED_FILE,
    UPLOADING_FILE,
    discover_jobs,
    load_job,
    mark_uploaded,
    schedule_retry,
    start_attempt,
)
from models import VideoUploadResult


def write_meta(directory: Path, content: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / META_FILE).write_text(content.strip() + "\n", encoding="utf-8")


def test_load_job_reads_basic_metadata(tmp_path: Path) -> None:
    job_dir = tmp_path / "job-1"
    video = job_dir / "video.mp4"

    write_meta(
        job_dir,
        """
# title
Test title

# description
Test description

# privacy
unlisted

# video_file
video.mp4

# priority
7
""",
    )
    video.write_bytes(b"fake video")

    job = load_job(job_dir)

    assert job.title == "Test title"
    assert job.description == "Test description"
    assert job.privacy == "unlisted"
    assert job.video_file == video
    assert job.state.base_priority == 7
    assert job.state.current_priority == 7


def test_load_job_uses_video_stem_as_default_title(tmp_path: Path) -> None:
    job_dir = tmp_path / "job-1"
    video = job_dir / "my-video.mp4"

    write_meta(
        job_dir,
        """
# privacy
private

# video_file
my-video.mp4
""",
    )
    video.write_bytes(b"fake video")

    job = load_job(job_dir)

    assert job.title == "my-video"


def test_load_job_rejects_bad_privacy(tmp_path: Path) -> None:
    job_dir = tmp_path / "job-1"
    video = job_dir / "video.mp4"

    write_meta(
        job_dir,
        """
# privacy
friends-only

# video_file
video.mp4
""",
    )
    video.write_bytes(b"fake video")

    try:
        load_job(job_dir)
    except Exception as exc:
        assert "bad privacy" in str(exc)
    else:
        raise AssertionError("load_job should reject bad privacy")


def test_start_attempt_writes_uploading_file(tmp_path: Path) -> None:
    job_dir = tmp_path / "job-1"
    video = job_dir / "video.mp4"

    write_meta(
        job_dir,
        """
# privacy
private

# video_file
video.mp4
""",
    )
    video.write_bytes(b"fake video")

    job = load_job(job_dir)
    start_attempt(job)

    content = (job_dir / UPLOADING_FILE).read_text(encoding="utf-8")

    assert "attempts: 1" in content
    assert "current_priority: -1" in content


def test_schedule_retry_writes_next_retry_at(tmp_path: Path) -> None:
    job_dir = tmp_path / "job-1"
    video = job_dir / "video.mp4"

    write_meta(
        job_dir,
        """
# privacy
private

# video_file
video.mp4
""",
    )
    video.write_bytes(b"fake video")

    job = load_job(job_dir)
    start_attempt(job)
    schedule_retry(job, Config(), "boom")

    content = (job_dir / UPLOADING_FILE).read_text(encoding="utf-8")

    assert "attempts: 1" in content
    assert "last_error: boom" in content
    assert "next_retry_at:" in content


def test_mark_uploaded_writes_uploaded_file_and_removes_uploading(tmp_path: Path) -> None:
    job_dir = tmp_path / "job-1"
    video = job_dir / "video.mp4"

    write_meta(
        job_dir,
        """
# privacy
unlisted

# video_file
video.mp4
""",
    )
    video.write_bytes(b"fake video")

    job = load_job(job_dir)
    start_attempt(job)

    mark_uploaded(job, VideoUploadResult(video_id="abc123", url="https://youtu.be/abc123"))

    uploaded = (job_dir / UPLOADED_FILE).read_text(encoding="utf-8")

    assert "video_id: abc123" in uploaded
    assert "url: https://youtu.be/abc123" in uploaded
    assert not (job_dir / UPLOADING_FILE).exists()


def test_discover_jobs_skips_uploaded_and_failed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(jobs, "WORKSPACE", tmp_path)

    ready_dir = tmp_path / "ready"
    uploaded_dir = tmp_path / "uploaded"
    failed_dir = tmp_path / "failed"

    for directory in (ready_dir, uploaded_dir, failed_dir):
        video = directory / "video.mp4"
        write_meta(
            directory,
            """
# privacy
private

# video_file
video.mp4
""",
        )
        video.write_bytes(b"fake video")

    (uploaded_dir / UPLOADED_FILE).write_text("uploaded\n", encoding="utf-8")
    (failed_dir / FAILED_FILE).write_text("failed\n", encoding="utf-8")

    found = discover_jobs()

    assert [job.directory.name for job in found] == ["ready"]
