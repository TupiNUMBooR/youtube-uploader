from __future__ import annotations

import json
import urllib.parse
import urllib.request

from dataclasses import dataclass

from logger import Logger


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

    def notify(self, text: str, logger: Logger) -> None:
        try:
            if not self.enabled:
                logger.write("telegram disabled")
                return

            message_id = self.send(text)
            logger.write(f"telegram send ok: message_id={message_id}")

        except Exception as exc:
            logger.write(f"telegram send failed: {type(exc).__name__}: {exc}")

    def send(self, text: str) -> int:
        payload = self._post(
            "sendMessage",
            {
                "chat_id": self.config.chat_id,
                "disable_web_page_preview": "false",
                "text": text,
            },
        )

        return int(payload["result"]["message_id"])

    def _post(self, method: str, fields: dict[str, str]) -> dict:
        url = f"https://api.telegram.org/bot{self.config.bot_token}/{method}"
        data = urllib.parse.urlencode(fields).encode("utf-8")

        with urllib.request.urlopen(url, data=data, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
