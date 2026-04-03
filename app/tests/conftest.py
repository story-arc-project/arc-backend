import pytest
from fakeredis import FakeRedis
from unittest.mock import MagicMock, patch

@pytest.fixture(autouse=True)
def fake_redis():
    fake = FakeRedis(decode_responses=True)
    
    with patch("src.db.red.r", fake):
        yield fake

@pytest.fixture(autouse=True)
def mock_mail():
    with patch("src.utils.mail.smtplib.SMTP") as mock_smtp, \
        patch("src.utils.mail.getenv") as mock_getenv:

        def fake_env(key: str):
            return {
                "GMAIL": "test@gmail.com",
                "GMAIL_PASSWORD": "password"
            }.get(key)

        mock_getenv.side_effect = fake_env

        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        mock_server.send_message.return_value = {}

        yield mock_server

@pytest.fixture(autouse=True)
def mock_jwt_key():
    with patch("src.utils.token.getenv") as mock_getenv:
        def fake_env(key: str):
            return {
                "JWT_KEY": "fakejwtkeyfakejwtkeyfakejwtkeyfakejwtkey",
                "HMAC_KEY": "fakehmackeyfakehmackeyfakehmackeyfakehmackey"
            }.get(key)
        
        mock_getenv.side_effect = fake_env

        yield mock_getenv

@pytest.fixture(autouse=True)
def dev_env():
    with patch("src.api.auth.getenv") as mock_getenv:
        def fake_env(key: str, default):
            return {
                "ENVIRONMENT": "development"
            }.get(key, default)
        
        mock_getenv.side_effect = fake_env

        yield mock_getenv