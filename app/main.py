#!/usr/bin/env python3
from __future__ import annotations

import os
import signal
import threading
import time
import traceback

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from telegram import Telegram, TelegramConfig
from youtube_api import upload_video, validate_token

WORKSPACE = Path("/workspace")

META_FILE = "youtube-uploader.md"
UPLOADING_FILE = "youtube-uploader-uploading.txt"
UPLOADED_FILE = "youtube-uploader-uploaded.txt"
FAILED_FILE = "youtube-uploader-failed.txt"
LOG_FILE = "youtube-uploader.log"

PRIVACY_VALUES = {"private", "unlisted", "public"}
THUMBNAIL_MAX_BYTES = 2_097_152

stop_event = threading.Event()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(dt: datetime | None = None) -> str:
    return (
        (dt or utc_now())
        .astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def parse_iso_utc(value: str) -> datetime:
    value = value.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"

    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)


def env_int(name: str, default: int) -> int:
    value = os.environ.get(name, "").strip()
    if not value:
        return default

    try:
        return int(value)
    except ValueError:
        raise ValueError(f"{name} must be an integer, got: {value!r}")


@dataclass(frozen=True)
class Config:
    version: str = os.environ.get("VERSION", "dev").strip() or "dev"
    poll_seconds: int = env_int("POLL_SECONDS", 5)
    max_upload_attempts: int = env_int("MAX_UPLOAD_ATTEMPTS", 20)
    retry_base_seconds: int = env_int("RETRY_BASE_SECONDS", 60)
    retry_max_seconds: int = env_int("RETRY_MAX_SECONDS", 3600)
    telegram_bot_token: str = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    telegram_chat_id: str = os.environ.get("TELEGRAM_CHAT_ID", "").strip()


@dataclass
class UploadState:
    attempts: int = 0
    base_priority: int = 0
    next_retry_at: datetime | None = None
    last_error: str = ""

    @property
    def current_priority(self) -> int:
        return self.base_priority - self.attempts


@dataclass
class UploadJob:
    directory: Path
    meta: dict[str, str]
    video_file: Path
    thumbnail_file: Path | None
    state: UploadState

    @property
    def title(self) -> str:
        return self.meta.get("title", "").strip() or self.video_file.stem

    @property
    def description(self) -> str:
        return self.meta.get("description", "").strip()

    @property
    def privacy(self) -> str:
        return self.meta.get("privacy", "").strip()

    @property
    def upload_since(self) -> datetime | None:
        raw = self.meta.get("upload_since", "").strip()
        return parse_iso_utc(raw) if raw else None

    @property
    def publish_at(self) -> datetime | None:
        raw = self.meta.get("publish_at", "").strip()
        return parse_iso_utc(raw) if raw else None

    @property
    def publish_at_iso(self) -> str | None:
        return iso_utc(self.publish_at) if self.publish_at else None


class JobError(Exception):
    pass


def request_stop(_signum, _frame) -> None:
    stop_event.set()


class Logger:
    def __init__(self, path: Path) -> None:
        self.path = path

    def write(self, message: str) -> None:
        line = f"[{iso_utc()}] {message}"
        print(line, flush=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def tail(self, lines: int = 10) -> str:
        if not self.path.exists():
            return ""

        content = self.path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(content[-lines:])


class StartupLogger:
    def write(self, message: str) -> None:
        print(f"[{iso_utc()}] {message}", flush=True)


def parse_markdown_metadata(path: Path) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current: str | None = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if raw_line.startswith("# "):
            current = raw_line[2:].strip().lower()
            sections.setdefault(current, [])
            continue

        if current is not None:
            sections[current].append(raw_line)

    return {key: "\n".join(value).strip() for key, value in sections.items()}


def parse_state_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        key, separator, value = line.partition(":")
        if separator:
            result[key.strip()] = value.strip()

    return result


def read_upload_state(directory: Path, base_priority: int) -> UploadState:
    raw = parse_state_file(directory / UPLOADING_FILE)

    return UploadState(
        attempts=int(raw["attempts"]) if raw.get("attempts") else 0,
        base_priority=int(raw["base_priority"]) if raw.get("base_priority") else base_priority,
        next_retry_at=parse_iso_utc(raw["next_retry_at"]) if raw.get("next_retry_at") else None,
        last_error=raw.get("last_error", ""),
    )


def write_upload_state(job: UploadJob) -> None:
    state = job.state
    lines = [
        f"updated_at: {iso_utc()}",
        f"attempts: {state.attempts}",
        f"base_priority: {state.base_priority}",
        f"current_priority: {state.current_priority}",
    ]

    if state.next_retry_at:
        lines.append(f"next_retry_at: {iso_utc(state.next_retry_at)}")
    if state.last_error:
        lines.append(f"last_error: {state.last_error}")

    (job.directory / UPLOADING_FILE).write_text("\n".join(lines) + "\n", encoding="utf-8")


def retry_delay(config: Config, attempts: int) -> int:
    return min(config.retry_base_seconds * (2 ** max(0, attempts - 1)), config.retry_max_seconds)


def resolve_declared_file(directory: Path, meta: dict[str, str], key: str, required: bool) -> Path | None:
    raw = meta.get(key, "").strip()
    if not raw:
        if required:
            raise JobError(f"{key} is mandatory")
        return None

    path = directory / raw
    if not path.is_file():
        raise JobError(f"{key} points to missing file: {raw}")

    return path


def load_job(directory: Path) -> UploadJob:
    meta = parse_markdown_metadata(directory / META_FILE)

    video_file = resolve_declared_file(directory, meta, "video_file", required=True)
    thumbnail_file = resolve_declared_file(directory, meta, "thumbnail_file", required=False)

    if video_file is None:
        raise JobError("video_file resolved to nothing")

    if thumbnail_file and thumbnail_file.stat().st_size > THUMBNAIL_MAX_BYTES:
        raise JobError(f"thumbnail_file is too large: {thumbnail_file.name}; max is {THUMBNAIL_MAX_BYTES} bytes")

    privacy = meta.get("privacy", "").strip()
    if not privacy:
        raise JobError("privacy is mandatory: private | unlisted | public")
    if privacy not in PRIVACY_VALUES:
        raise JobError(f"bad privacy: {privacy!r}; expected private | unlisted | public")

    if meta.get("priority", "").strip():
        int(meta["priority"].strip())
    if meta.get("upload_since", "").strip():
        parse_iso_utc(meta["upload_since"])
    if meta.get("publish_at", "").strip():
        parse_iso_utc(meta["publish_at"])

    priority = int(meta.get("priority", "").strip() or "0")

    return UploadJob(
        directory=directory,
        meta=meta,
        video_file=video_file,
        thumbnail_file=thumbnail_file,
        state=read_upload_state(directory, priority),
    )


def mark_validation_failed(directory: Path, message: str) -> None:
    logger = Logger(directory / LOG_FILE)
    logger.write(f"validation failed: {message}")

    (directory / FAILED_FILE).write_text(
        "\n".join(
            [
                f"failed_at: {iso_utc()}",
                "stage: validation",
                f"message: {message}",
                "last_log_lines:",
                logger.tail(10),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    uploading = directory / UPLOADING_FILE
    if uploading.exists():
        uploading.unlink()


def discover_jobs() -> list[UploadJob]:
    jobs: list[UploadJob] = []
    now = utc_now()

    for directory in sorted(p for p in WORKSPACE.iterdir() if p.is_dir()):
        if (directory / UPLOADED_FILE).exists() or (directory / FAILED_FILE).exists():
            continue

        if not (directory / META_FILE).exists():
            continue

        try:
            job = load_job(directory)
        except Exception as exc:
            mark_validation_failed(directory, str(exc))
            continue

        if job.upload_since and now < job.upload_since:
            continue

        if job.state.next_retry_at and now < job.state.next_retry_at:
            continue

        jobs.append(job)

    jobs.sort(key=lambda j: (-j.state.current_priority, j.directory.stat().st_mtime, j.directory.name))
    return jobs


def mark_uploaded(job: UploadJob, video_id: str, url: str) -> None:
    content = [
        f"uploaded_at: {iso_utc()}",
        f"video_id: {video_id}",
        f"url: {url}",
        f"privacy: {job.privacy}",
    ]

    if job.publish_at:
        content.append(f"publish_at: {iso_utc(job.publish_at)}")

    (job.directory / UPLOADED_FILE).write_text("\n".join(content) + "\n", encoding="utf-8")

    for marker in (UPLOADING_FILE, FAILED_FILE):
        path = job.directory / marker
        if path.exists():
            path.unlink()


def mark_failed(job: UploadJob, message: str, logger: Logger) -> None:
    (job.directory / FAILED_FILE).write_text(
        "\n".join(
            [
                f"failed_at: {iso_utc()}",
                "stage: upload",
                f"attempts: {job.state.attempts}",
                f"message: {message}",
                "last_log_lines:",
                logger.tail(10),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    uploading = job.directory / UPLOADING_FILE
    if uploading.exists():
        uploading.unlink()


def telegram_send(telegram: Telegram, text: str, logger: Logger | StartupLogger) -> None:
    try:
        message_id = telegram.send(text)
        logger.write("telegram send ok" if message_id is not None else "telegram disabled")
    except Exception as exc:
        logger.write(f"telegram send failed: {type(exc).__name__}: {exc}")


def process_one(job: UploadJob, config: Config, telegram: Telegram) -> bool:
    logger = Logger(job.directory / LOG_FILE)

    telegram_send(
        telegram,
        f"📼 YouTube upload started\n"
        f"folder: {job.directory.name}\n"
        f"video: {job.video_file.name}\n"
        f"title: {job.title}\n"
        f"privacy: {job.privacy}\n"
        f"priority: {job.state.current_priority}",
        logger,
    )

    try:
        job.state.attempts += 1
        job.state.next_retry_at = None
        job.state.last_error = ""
        write_upload_state(job)

        logger.write(f"attempt {job.state.attempts}/{config.max_upload_attempts} started")

        video_id, url = upload_video(job, logger)
        mark_uploaded(job, video_id, url)

        telegram_send(
            telegram,
            f"✅ YouTube upload complete\n"
            f"folder: {job.directory.name}\n"
            f"title: {job.title}\n"
            f"url: {url}",
            logger,
        )

        logger.write("upload job complete")
        return True

    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        logger.write(f"attempt {job.state.attempts}/{config.max_upload_attempts} failed: {message}")
        logger.write(traceback.format_exc().rstrip())

        job.state.last_error = message

        if job.state.attempts >= config.max_upload_attempts:
            mark_failed(job, message, logger)
            telegram_send(
                telegram,
                f"❌ YouTube upload failed\n"
                f"folder: {job.directory.name}\n"
                f"title: {job.title}\n"
                f"attempts: {job.state.attempts}/{config.max_upload_attempts}\n"
                f"last 10 log lines:\n{logger.tail(10)}",
                logger,
            )
            return False

        delay = retry_delay(config, job.state.attempts)
        job.state.next_retry_at = utc_now() + timedelta(seconds=delay)
        write_upload_state(job)

        telegram_send(
            telegram,
            f"⚠️ YouTube upload retry scheduled\n"
            f"folder: {job.directory.name}\n"
            f"title: {job.title}\n"
            f"attempts: {job.state.attempts}/{config.max_upload_attempts}\n"
            f"current_priority: {job.state.current_priority}\n"
            f"next_retry_at: {iso_utc(job.state.next_retry_at)}\n"
            f"error: {message}",
            logger,
        )

        return False


def create_telegram(config: Config) -> Telegram:
    return Telegram(TelegramConfig(bot_token=config.telegram_bot_token, chat_id=config.telegram_chat_id))


def main() -> int:
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    config = Config()
    telegram = create_telegram(config)
    startup_logger = StartupLogger()

    startup_logger.write(f"youtube-uploader v{config.version} started")
    validate_token(startup_logger)
    telegram_send(telegram, f"🛎️ youtube-uploader v{config.version} started and validated", startup_logger)

    while not stop_event.is_set():
        try:
            jobs = discover_jobs()
            if jobs:
                process_one(jobs[0], config, telegram)

            stop_event.wait(config.poll_seconds)

        except KeyboardInterrupt:
            stop_event.set()

        except Exception as exc:
            startup_logger.write(f"main loop error: {type(exc).__name__}: {exc}")
            startup_logger.write(traceback.format_exc().rstrip())
            telegram_send(telegram, f"❌ youtube-uploader main loop error\n{type(exc).__name__}: {exc}", startup_logger)
            stop_event.wait(config.retry_base_seconds)

    startup_logger.write("stopped")
    telegram_send(telegram, f"🛑 youtube-uploader v{config.version} stopped", startup_logger)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
