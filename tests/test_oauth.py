from pathlib import Path
from unittest.mock import Mock, patch

from youtube_uploader import oauth


def test_create_token_uses_detected_handle(tmp_path: Path, monkeypatch) -> None:
    auth_dir = tmp_path / ".auth"
    client_secret_file = auth_dir / "client_secret.json"

    monkeypatch.setattr(oauth, "AUTH_DIR", auth_dir)
    monkeypatch.setattr(oauth, "CLIENT_SECRET_FILE", client_secret_file)
    monkeypatch.setattr(oauth, "PORT", 4444)

    auth_dir.mkdir()
    client_secret_file.write_text("{}", encoding="utf-8")

    creds = Mock()
    creds.to_json.return_value = '{"token":"test"}'

    flow = Mock()
    flow.run_local_server.return_value = creds

    with (
        patch.object(oauth.InstalledAppFlow, "from_client_secrets_file", return_value=flow) as factory,
        patch.object(oauth, "detect_channel", return_value=("@test", "UC123", "Test channel")),
    ):
        token_file = oauth.create_token()

    assert token_file == auth_dir / "token.@test.json"
    assert token_file.read_text(encoding="utf-8") == '{"token":"test"}'

    factory.assert_called_once_with(str(client_secret_file), oauth.SCOPES)
    flow.run_local_server.assert_called_once_with(
        host="localhost",
        bind_addr="0.0.0.0",
        port=4444,
        open_browser=False,
    )


def test_detect_channel_requires_handle() -> None:
    creds = Mock()
    youtube = Mock()
    youtube.channels.return_value.list.return_value.execute.return_value = {
        "items": [{"id": "UC123", "snippet": {"title": "No handle"}}]
    }

    with patch.object(oauth, "build", return_value=youtube):
        try:
            oauth.detect_channel(creds)
        except RuntimeError as exc:
            assert "handle is missing or invalid" in str(exc)
        else:
            raise AssertionError("detect_channel should reject missing handle")
