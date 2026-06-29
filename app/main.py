#!/usr/bin/env python3
from __future__ import annotations

import signal
import threading
import traceback
import os
from pathlib import Path

from jobs import DEFAULT_JOB_DIR, LOG_FILE, JobError, UploadJob, load_job
from logger import Logger
from youtube_api import VideoUploadRequest, VideoUploadResult, upload_video, validate_token

stop_event = threading.Event()
VERSION = os.environ.get("VERSION", "dev").strip() or "dev"


def request_stop(_signum, _frame) -> None:
    stop_event.set()


def upload_job(job: UploadJob) -> VideoUploadResult:
    logger = Logger(job.directory / LOG_FILE)

    logger.write("upload started")
    request = VideoUploadRequest(
        video_file=job.video_file,
        thumbnail_file=job.thumbnail_file,
        title=job.title,
        description=job.description,
        privacy=job.privacy,
        publish_at=job.publish_at,
    )
    result = upload_video(request, logger)
    logger.write(f"upload complete: {result.url}")

    return result


def parse_job_dir(argv: list[str] | None = None) -> Path:
    args = argv if argv is not None else []
    if len(args) > 1:
        raise JobError("usage: main.py [job_dir]")
    return Path(args[0]) if args else DEFAULT_JOB_DIR


def main(argv: list[str] | None = None) -> int:
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    logger = Logger()

    logger.write(f"youtube-uploader v{VERSION} started")

    try:
        job_dir = parse_job_dir(argv)
        validate_token(logger)
        logger.write(f"youtube-uploader v{VERSION} validated")

        job = load_job(job_dir)
        result = upload_job(job)

        logger.write(f"video_id: {result.video_id}")
        logger.write(f"url: {result.url}")
        return 0

    except KeyboardInterrupt:
        logger.write("interrupted")
        return 130

    except Exception as exc:
        logger.write(f"failed: {type(exc).__name__}: {exc}")
        logger.write(traceback.format_exc().rstrip())
        return 1


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
