from __future__ import annotations

from pathlib import Path

import jobs
from jobs import (
    META_FILE,
    load_job,
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

""",
    )
    video.write_bytes(b"fake video")

    job = load_job(job_dir)

    assert job.title == "Test title"
    assert job.description == "Test description"
    assert job.privacy == "unlisted"
    assert job.video_file == video


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


def test_load_job_rejects_missing_video(tmp_path: Path) -> None:
    job_dir = tmp_path / "bad"
    write_meta(
        job_dir,
        """
# privacy
private

# video_file
missing.mp4
""",
    )

    try:
        load_job(job_dir)
    except Exception as exc:
        assert "video_file points to missing file" in str(exc)
    else:
        raise AssertionError("load_job should reject missing video")


def test_load_job_rejects_missing_metadata(tmp_path: Path) -> None:
    job_dir = tmp_path / "job-1"
    job_dir.mkdir()

    try:
        load_job(job_dir)
    except Exception as exc:
        assert "metadata file not found" in str(exc)
    else:
        raise AssertionError("load_job should reject missing metadata")
