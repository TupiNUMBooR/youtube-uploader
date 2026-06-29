from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from time_utils import parse_iso_utc

DEFAULT_JOB_DIR = Path('/job')

META_FILE = 'youtube-uploader.md'
LOG_FILE = 'youtube-uploader.log'

PRIVACY_VALUES = {'private', 'unlisted', 'public'}
THUMBNAIL_MAX_BYTES = 2_097_152


class JobError(Exception):
    pass


@dataclass
class UploadJob:
    directory: Path
    meta: dict[str, str]
    video_file: Path
    thumbnail_file: Path | None

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
    def publish_at(self) -> datetime | None:
        raw = self.meta.get("publish_at", "").strip()
        return parse_iso_utc(raw) if raw else None


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
    metadata_file = directory / META_FILE
    if not directory.is_dir():
        raise JobError(f'job directory not found: {directory}')
    if not metadata_file.is_file():
        raise JobError(f'metadata file not found: {metadata_file}')

    meta = parse_markdown_metadata(metadata_file)
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
    if meta.get('publish_at', '').strip():
        parse_iso_utc(meta['publish_at'])
    return UploadJob(directory=directory, meta=meta, video_file=video_file, thumbnail_file=thumbnail_file)
