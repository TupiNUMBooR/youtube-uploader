from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from time_utils import iso_utc, parse_iso_utc


@dataclass
class UploadState:
    attempts: int = 0
    base_priority: int = 0
    next_retry_at: datetime | None = None
    last_error: str = ""

    @property
    def current_priority(self) -> int:
        return self.base_priority - self.attempts


@dataclass(frozen=True)
class VideoUploadRequest:
    video_file: Path
    thumbnail_file: Path | None
    title: str
    description: str
    privacy: str
    publish_at: datetime | None

    @property
    def publish_at_iso(self) -> str | None:
        return iso_utc(self.publish_at) if self.publish_at else None


@dataclass(frozen=True)
class VideoUploadResult:
    video_id: str
    url: str


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

    def to_upload_request(self) -> VideoUploadRequest:
        return VideoUploadRequest(
            video_file=self.video_file,
            thumbnail_file=self.thumbnail_file,
            title=self.title,
            description=self.description,
            privacy=self.privacy,
            publish_at=self.publish_at,
        )
