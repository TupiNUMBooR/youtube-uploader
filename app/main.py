#!/usr/bin/env python3
from __future__ import annotations

import signal
import threading
import traceback
from time_utils import iso_utc

from config import Config
from jobs import LOG_FILE, discover_jobs, mark_failed, mark_uploaded, schedule_retry, start_attempt
from logger import Logger
from models import UploadJob
from telegram import Telegram, TelegramConfig
from youtube_api import upload_video, validate_token

stop_event = threading.Event()


def request_stop(_signum, _frame) -> None:
    stop_event.set()


def create_telegram(config: Config) -> Telegram:
    return Telegram(TelegramConfig(bot_token=config.telegram_bot_token, chat_id=config.telegram_chat_id))


def upload_started_message(job: UploadJob) -> str:
    return (
        f"📼 YouTube upload started\n"
        f"folder: {job.directory.name}\n"
        f"video: {job.video_file.name}\n"
        f"title: {job.title}\n"
        f"privacy: {job.privacy}\n"
        f"priority: {job.state.current_priority}"
    )


def upload_complete_message(job: UploadJob, url: str) -> str:
    return (
        f"✅ YouTube upload complete\n"
        f"folder: {job.directory.name}\n"
        f"title: {job.title}\n"
        f"url: {url}"
    )


def upload_failed_message(job: UploadJob, config: Config, logger: Logger) -> str:
    return (
        f"❌ YouTube upload failed\n"
        f"folder: {job.directory.name}\n"
        f"title: {job.title}\n"
        f"attempts: {job.state.attempts}/{config.max_upload_attempts}\n"
        f"last 10 log lines:\n{logger.tail(10)}"
    )


def retry_scheduled_message(job: UploadJob, config: Config, message: str) -> str:
    return (
        f"⚠️ YouTube upload retry scheduled\n"
        f"folder: {job.directory.name}\n"
        f"title: {job.title}\n"
        f"attempts: {job.state.attempts}/{config.max_upload_attempts}\n"
        f"current_priority: {job.state.current_priority}\n"
        f"next_retry_at: {iso_utc(job.state.next_retry_at) if job.state.next_retry_at else ''}\n"
        f"error: {message}"
    )


def process_one(job: UploadJob, config: Config, telegram: Telegram) -> bool:
    logger = Logger(job.directory / LOG_FILE)

    telegram.notify(upload_started_message(job), logger)

    try:
        start_attempt(job)

        logger.write(f"attempt {job.state.attempts}/{config.max_upload_attempts} started")

        result = upload_video(job.to_upload_request(), logger)
        mark_uploaded(job, result)

        telegram.notify(upload_complete_message(job, result.url), logger)

        logger.write("upload job complete")
        return True

    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        logger.write(f"attempt {job.state.attempts}/{config.max_upload_attempts} failed: {message}")
        logger.write(traceback.format_exc().rstrip())

        job.state.last_error = message

        if job.state.attempts >= config.max_upload_attempts:
            mark_failed(job, message, logger)
            telegram.notify(upload_failed_message(job, config, logger), logger)
            return False

        schedule_retry(job, config, message)
        telegram.notify(retry_scheduled_message(job, config, message), logger)

        return False


def main() -> int:
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    config = Config()
    telegram = create_telegram(config)
    logger = Logger()

    logger.write(f"youtube-uploader v{config.version} started")
    validate_token(logger)
    telegram.notify(f"🛎️ youtube-uploader v{config.version} started and validated", logger)

    while not stop_event.is_set():
        try:
            jobs = discover_jobs()
            if jobs:
                process_one(jobs[0], config, telegram)

            stop_event.wait(config.poll_seconds)

        except KeyboardInterrupt:
            stop_event.set()

        except Exception as exc:
            logger.write(f"main loop error: {type(exc).__name__}: {exc}")
            logger.write(traceback.format_exc().rstrip())
            telegram.notify(f"❌ youtube-uploader main loop error\n{type(exc).__name__}: {exc}", logger)
            stop_event.wait(config.retry_base_seconds)

    logger.write("stopped")
    telegram.notify(f"🛑 youtube-uploader v{config.version} stopped", logger)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
