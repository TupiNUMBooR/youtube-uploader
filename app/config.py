from __future__ import annotations

import os
from dataclasses import dataclass


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
