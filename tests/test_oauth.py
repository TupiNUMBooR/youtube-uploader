from unittest.mock import Mock, patch

from app import oauth


def test_create_token_writes_token(tmp_path, monkeypatch):
    auth_dir = tmp_path / ".auth"
    client_secret_file = auth_dir / "client_secret.json"
    token_file = auth_dir / "token.json"

    monkeypatch.setattr(oauth, "AUTH_DIR", auth_dir)
    monkeypatch.setattr(oauth, "CLIENT_SECRET_FILE", client_secret_file)
    monkeypatch.setattr(oauth, "TOKEN_FILE", token_file)
    monkeypatch.setattr(oauth, "PORT", 8080)

    auth_dir.mkdir()
    client_secret_file.write_text("{}", encoding="utf-8")

    creds = Mock()
    creds.to_json.return_value = '{"token":"test"}'

    flow = Mock()
    flow.run_local_server.return_value = creds

    with patch.object(
        oauth.InstalledAppFlow,
        "from_client_secrets_file",
        return_value=flow,
    ) as from_client_secrets_file:
        oauth.create_token()

    assert token_file.read_text(encoding="utf-8") == '{"token":"test"}'

    from_client_secrets_file.assert_called_once_with(
        str(client_secret_file),
        ["https://www.googleapis.com/auth/youtube.upload"],
    )

    flow.run_local_server.assert_called_once_with(
        host="localhost",
        bind_addr="0.0.0.0",
        port=8080,
        open_browser=False,
    )
