from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True)
class TelegramConfig:
    bot_token: str
    chat_id: str


class Telegram:
    def __init__(self, config: TelegramConfig) -> None:
        self.config = config

    @property
    def enabled(self) -> bool:
        return bool(self.config.bot_token and self.config.chat_id)

    def send(self, text: str) -> int | None:
        if not self.enabled:
            return None

        payload = self._post(
            "sendMessage",
            {
                "chat_id": self.config.chat_id,
                "disable_web_page_preview": "false",
                "text": text,
            },
        )

        return int(payload["result"]["message_id"])

    def edit(self, message_id: int | None, text: str) -> None:
        if not self.enabled or message_id is None:
            return

        self._post(
            "editMessageText",
            {
                "chat_id": self.config.chat_id,
                "message_id": str(message_id),
                "disable_web_page_preview": "false",
                "text": text,
            },
        )

    def _post(self, method: str, fields: dict[str, str]) -> dict:
        url = f"https://api.telegram.org/bot{self.config.bot_token}/{method}"
        data = urllib.parse.urlencode(fields).encode()

        with urllib.request.urlopen(url, data=data, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
