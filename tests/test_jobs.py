from __future__ import annotations

from pathlib import Path

import jobs
from config import Config
from jobs import (
    META_FILE,
    UPLOADING_FILE,
    discover_jobs,
    load_job,
    mark_uploaded,
    schedule_retry,
    start_attempt,
)


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
    assert "next_retry_at:" in content


def test_mark_uploaded_moves_job_and_removes_uploading(tmp_path: Path, monkeypatch) -> None:
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

    out_dir = tmp_path / "out"
    monkeypatch.setattr(jobs, "OUT_DIR", out_dir)

    mark_uploaded(job)

    assert not (job_dir / UPLOADING_FILE).exists()
    assert (out_dir / "job-1").exists()


def test_discover_jobs_finds_ready_jobs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(jobs, "IN_DIR", tmp_path)

    ready_dir = tmp_path / "ready"

    for directory in (ready_dir,):
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

    found = discover_jobs()

    assert [job.directory.name for job in found] == ["ready"]


def test_load_job_rejects_large_thumbnail(tmp_path: Path) -> None:
    job_dir = tmp_path / "job-1"
    video = job_dir / "video.mp4"
    thumbnail = job_dir / "thumbnail.jpg"

    write_meta(
        job_dir,
        """
# privacy
private

# video_file
video.mp4

# thumbnail_file
thumbnail.jpg
""",
    )
    video.write_bytes(b"fake video")
    thumbnail.write_bytes(b"x" * (jobs.THUMBNAIL_MAX_BYTES + 1))

    try:
        load_job(job_dir)
    except Exception as exc:
        assert "thumbnail_file is too large" in str(exc)
    else:
        raise AssertionError("load_job should reject large thumbnail")


def test_discover_jobs_skips_future_upload_since(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(jobs, "IN_DIR", tmp_path)

    job_dir = tmp_path / "future"
    video = job_dir / "video.mp4"

    write_meta(
        job_dir,
        """
# privacy
private

# video_file
video.mp4

# upload_since
2999-01-01T00:00:00Z
""",
    )
    video.write_bytes(b"fake video")

    found = discover_jobs()

    assert found == []


def test_discover_jobs_retries_validation_for_non_atomic_move(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(jobs, "IN_DIR", tmp_path)

    sleep_calls: list[int] = []
    job_dir = tmp_path / "late-video"
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

    def fake_sleep(seconds: int) -> None:
        sleep_calls.append(seconds)
        if seconds == 1:
            video.write_bytes(b"fake video")

    monkeypatch.setattr(jobs.time, "sleep", fake_sleep)

    found = discover_jobs()

    assert [job.directory.name for job in found] == ["late-video"]
    assert sleep_calls == [1]
    assert job_dir.exists()


def test_discover_jobs_moves_invalid_job_to_fail(tmp_path: Path, monkeypatch) -> None:
    in_dir = tmp_path / "in"
    fail_dir = tmp_path / "fail"
    sleep_calls: list[int] = []

    monkeypatch.setattr(jobs, "IN_DIR", in_dir)
    monkeypatch.setattr(jobs, "FAIL_DIR", fail_dir)
    monkeypatch.setattr(jobs.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    job_dir = in_dir / "bad"
    write_meta(
        job_dir,
        """
# privacy
private

# video_file
missing.mp4
""",
    )

    found = discover_jobs()

    assert found == []
    assert sleep_calls == [1, 2, 4, 8]
    assert not job_dir.exists()
    assert (fail_dir / "bad").exists()
    assert (fail_dir / "bad" / jobs.LOG_FILE).exists()


def test_discover_jobs_sorts_by_priority_desc(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(jobs, "IN_DIR", tmp_path)

    for name, priority in (("low", 1), ("high", 10)):
        directory = tmp_path / name
        video = directory / "video.mp4"

        write_meta(
            directory,
            f"""
# privacy
private

# video_file
video.mp4

# priority
{priority}
""",
        )
        video.write_bytes(b"fake video")

    found = discover_jobs()

    assert [job.directory.name for job in found] == ["high", "low"]
