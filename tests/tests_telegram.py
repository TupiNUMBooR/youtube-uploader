from __future__ import annotations

from unittest.mock import patch

from logger import Logger
from telegram import Telegram, TelegramConfig


def make_telegram() -> Telegram:
    return Telegram(
        TelegramConfig(
            bot_token="test-token",
            chat_id="123",
        )
    )


def test_enabled() -> None:
    telegram = make_telegram()

    assert telegram.enabled is True


def test_disabled_without_token() -> None:
    telegram = Telegram(TelegramConfig(bot_token="", chat_id="123"))

    assert telegram.enabled is False


def test_send_returns_message_id() -> None:
    telegram = make_telegram()

    with patch.object(
        telegram,
        "_post",
        return_value={"result": {"message_id": 777}},
    ) as post_mock:
        message_id = telegram.send("hello")

    assert message_id == 777

    post_mock.assert_called_once_with(
        "sendMessage",
        {
            "chat_id": "123",
            "disable_web_page_preview": "false",
            "text": "hello",
        },
    )


def test_notify_logs_disabled(tmp_path) -> None:
    telegram = Telegram(TelegramConfig(bot_token="", chat_id=""))

    log_file = tmp_path / "test.log"
    logger = Logger(log_file)

    telegram.notify("hello", logger)

    content = log_file.read_text(encoding="utf-8")

    assert "telegram disabled" in content


def test_notify_logs_success(tmp_path) -> None:
    telegram = make_telegram()

    log_file = tmp_path / "test.log"
    logger = Logger(log_file)

    with patch.object(telegram, "send", return_value=555) as send_mock:
        telegram.notify("hello", logger)

    send_mock.assert_called_once_with("hello")

    content = log_file.read_text(encoding="utf-8")

    assert "telegram send ok: message_id=555" in content


def test_notify_logs_failure(tmp_path) -> None:
    telegram = make_telegram()

    log_file = tmp_path / "test.log"
    logger = Logger(log_file)

    with patch.object(
        telegram,
        "send",
        side_effect=RuntimeError("boom"),
    ):
        telegram.notify("hello", logger)

    content = log_file.read_text(encoding="utf-8")

    assert "telegram send failed" in content
    assert "RuntimeError: boom" in content
