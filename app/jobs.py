from __future__ import annotations

import shutil
import time
from datetime import timedelta
from pathlib import Path

from config import Config
from logger import Logger
from models import UploadJob, UploadState
from time_utils import iso_utc, parse_iso_utc, utc_now

IN_DIR = Path('/in')
OUT_DIR = Path('/out')
FAIL_DIR = Path('/fail')

META_FILE = 'youtube-uploader.md'
UPLOADING_FILE = 'youtube-uploader-uploading.txt'
LOG_FILE = 'youtube-uploader.log'

PRIVACY_VALUES = {'private', 'unlisted', 'public'}
THUMBNAIL_MAX_BYTES = 2_097_152
VALIDATION_RETRY_DELAYS_SECONDS = (1, 2, 4, 8)


class JobError(Exception):
    pass


def parse_markdown_metadata(path: Path) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for raw_line in path.read_text(encoding='utf-8').splitlines():
        if raw_line.startswith('# '):
            current = raw_line[2:].strip().lower()
            sections.setdefault(current, [])
            continue
        if current is not None:
            sections[current].append(raw_line)
    return {key: '\n'.join(value).strip() for key, value in sections.items()}


def parse_state_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    result: dict[str, str] = {}
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        key, separator, value = line.partition(':')
        if separator:
            result[key.strip()] = value.strip()
    return result


def read_upload_state(directory: Path, base_priority: int) -> UploadState:
    raw = parse_state_file(directory / UPLOADING_FILE)
    return UploadState(
        attempts=int(raw['attempts']) if raw.get('attempts') else 0,
        base_priority=base_priority,
        next_retry_at=parse_iso_utc(raw['next_retry_at']) if raw.get('next_retry_at') else None,
    )


def write_upload_state(job: UploadJob) -> None:
    lines = [f'attempts: {job.state.attempts}']
    if job.state.next_retry_at:
        lines.append(f'next_retry_at: {iso_utc(job.state.next_retry_at)}')
    (job.directory / UPLOADING_FILE).write_text('\n'.join(lines) + '\n', encoding='utf-8')


def retry_delay(config: Config, attempts: int) -> int:
    return min(config.retry_base_seconds * (2 ** max(0, attempts - 1)), config.retry_max_seconds)


def schedule_retry(job: UploadJob, config: Config, _message: str) -> None:
    job.state.next_retry_at = utc_now() + timedelta(seconds=retry_delay(config, job.state.attempts))
    write_upload_state(job)


def start_attempt(job: UploadJob) -> None:
    job.state.attempts += 1
    job.state.next_retry_at = None
    write_upload_state(job)


def resolve_declared_file(directory: Path, meta: dict[str, str], key: str, required: bool) -> Path | None:
    raw = meta.get(key, '').strip()
    if not raw:
        if required:
            raise JobError(f'{key} is mandatory')
        return None
    path = directory / raw
    if not path.is_file():
        raise JobError(f'{key} points to missing file: {raw}')
    return path


def load_job(directory: Path) -> UploadJob:
    meta = parse_markdown_metadata(directory / META_FILE)
    video_file = resolve_declared_file(directory, meta, 'video_file', required=True)
    thumbnail_file = resolve_declared_file(directory, meta, 'thumbnail_file', required=False)
    if video_file is None:
        raise JobError('video_file resolved to nothing')
    if thumbnail_file and thumbnail_file.stat().st_size > THUMBNAIL_MAX_BYTES:
        raise JobError(f'thumbnail_file is too large: {thumbnail_file.name}; max is {THUMBNAIL_MAX_BYTES} bytes')
    privacy = meta.get('privacy', '').strip()
    if not privacy:
        raise JobError('privacy is mandatory: private | unlisted | public')
    if privacy not in PRIVACY_VALUES:
        raise JobError(f'bad privacy: {privacy!r}; expected private | unlisted | public')
    if meta.get('priority', '').strip():
        int(meta['priority'].strip())
    if meta.get('upload_since', '').strip():
        parse_iso_utc(meta['upload_since'])
    if meta.get('publish_at', '').strip():
        parse_iso_utc(meta['publish_at'])
    priority = int(meta.get('priority', '').strip() or '0')
    return UploadJob(directory=directory, meta=meta, video_file=video_file, thumbnail_file=thumbnail_file, state=read_upload_state(directory, priority))


def move_job(directory: Path, destination_root: Path) -> None:
    destination_root.mkdir(parents=True, exist_ok=True)
    shutil.move(str(directory), str(destination_root / directory.name))


def mark_validation_failed(directory: Path, message: str) -> None:
    logger = Logger(directory / LOG_FILE)
    logger.write(f'validation failed: {message}')
    uploading = directory / UPLOADING_FILE
    if uploading.exists():
        uploading.unlink()
    move_job(directory, FAIL_DIR)


def load_job_with_validation_retries(directory: Path) -> UploadJob:
    logger = Logger(directory / LOG_FILE)
    last_error: Exception | None = None

    for delay_seconds in (None, *VALIDATION_RETRY_DELAYS_SECONDS):
        if delay_seconds is not None:
            logger.write(f'validation retry waiting {delay_seconds}s')
            time.sleep(delay_seconds)

        try:
            return load_job(directory)
        except Exception as exc:
            last_error = exc
            logger.write(f'validation attempt failed: {exc}')

    if last_error is not None:
        raise last_error

    raise JobError('validation failed')


def discover_jobs() -> list[UploadJob]:
    jobs: list[UploadJob] = []
    now = utc_now()
    IN_DIR.mkdir(parents=True, exist_ok=True)
    for directory in sorted(p for p in IN_DIR.iterdir() if p.is_dir()):
        if not (directory / META_FILE).exists():
            continue
        try:
            job = load_job_with_validation_retries(directory)
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


def mark_uploaded(job: UploadJob) -> None:
    uploading = job.directory / UPLOADING_FILE
    if uploading.exists():
        uploading.unlink()
    move_job(job.directory, OUT_DIR)


def mark_failed(job: UploadJob, message: str, logger: Logger) -> None:
    logger.write(f'job permanently failed attempts={job.state.attempts} error={message}')
    uploading = job.directory / UPLOADING_FILE
    if uploading.exists():
        uploading.unlink()
    move_job(job.directory, FAIL_DIR)
