#!/usr/bin/env python3
from __future__ import annotations

import os

import uvicorn

from youtube_uploader.logger import error, log
from youtube_uploader.youtube_api import TokenError, discover_tokens

VERSION = os.environ.get("VERSION", "dev").strip() or "dev"
HOST = "0.0.0.0"
PORT = 8080


def main() -> int:
    try:
        tokens = discover_tokens()
        log(f"youtube-uploader v{VERSION} channels={len(tokens)}")
        uvicorn.run(
            "youtube_uploader.server:app",
            host=HOST,
            port=PORT,
            access_log=False,
        )
        return 0
    except TokenError as exc:
        error(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
