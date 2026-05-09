from __future__ import annotations

from pathlib import Path

from time_utils import iso_utc


class Logger:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path

    def write(self, message: str) -> None:
        line = f"[{iso_utc()}] {message}"
        print(line, flush=True)

        if self.path is None:
            return

        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def tail(self, lines: int = 10) -> str:
        if self.path is None or not self.path.exists():
            return ""

        content = self.path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(content[-lines:])
