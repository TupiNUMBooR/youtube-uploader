from __future__ import annotations

from unittest.mock import patch

from youtube_uploader import main


def test_main_validates_tokens_and_starts_server() -> None:
    with (
        patch.object(main, "discover_tokens", return_value={"@test": object()}) as discover_mock,
        patch.object(main.uvicorn, "run") as run_mock,
    ):
        result = main.main()

    assert result == 0
    discover_mock.assert_called_once_with()
    run_mock.assert_called_once_with(
        "youtube_uploader.server:app",
        host="0.0.0.0",
        port=8080,
        access_log=False,
    )


def test_main_returns_failure_for_bad_tokens() -> None:
    with patch.object(main, "discover_tokens", side_effect=main.TokenError("bad token")):
        assert main.main() == 1
