from __future__ import annotations

import sys

from time_utils import iso_utc

SERVICE_NAME = "youtube-uploader"


def log(message: str) -> None:
    print(f"[{iso_utc()}] [{SERVICE_NAME}] {message}", file=sys.stderr, flush=True)


def warn(message: str) -> None:
    log(f"[WARN] {message}")


def error(message: str) -> None:
    log(f"[ERROR] {message}")
