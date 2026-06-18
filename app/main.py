#!/usr/bin/env python3
from __future__ import annotations

import signal
import threading
import traceback

from config import Config
from jobs import LOG_FILE, discover_jobs, mark_failed, mark_uploaded, schedule_retry, start_attempt
from logger import Logger
from models import UploadJob
from youtube_api import upload_video, validate_token

stop_event = threading.Event()


def request_stop(_signum, _frame) -> None:
    stop_event.set()


def process_one(job: UploadJob, config: Config) -> bool:
    logger = Logger(job.directory / LOG_FILE)

    try:
        start_attempt(job)

        logger.write(f"attempt {job.state.attempts}/{config.max_upload_attempts} started")

        result = upload_video(job.to_upload_request(), logger)

        logger.write(f"upload succeeded video_id={result.video_id} url={result.url}")
        logger.write("upload job complete")

        mark_uploaded(job)

        return True

    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        logger.write(f"attempt {job.state.attempts}/{config.max_upload_attempts} failed: {message}")
        logger.write(traceback.format_exc().rstrip())

        job.state.last_error = message

        if job.state.attempts >= config.max_upload_attempts:
            mark_failed(job, message, logger)
            return False

        schedule_retry(job, config, message)
        return False


def main() -> int:
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    config = Config()
    logger = Logger()

    logger.write(f"youtube-uploader v{config.version} started")
    validate_token(logger)
    logger.write(f"youtube-uploader v{config.version} validated")

    while not stop_event.is_set():
        try:
            jobs = discover_jobs()
            if jobs:
                process_one(jobs[0], config)

            stop_event.wait(config.poll_seconds)

        except KeyboardInterrupt:
            stop_event.set()

        except Exception as exc:
            logger.write(f"main loop error: {type(exc).__name__}: {exc}")
            logger.write(traceback.format_exc().rstrip())
            stop_event.wait(config.retry_base_seconds)

    logger.write("stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
