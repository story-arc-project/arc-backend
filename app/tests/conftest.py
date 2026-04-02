import pytest
from fakeredis import FakeRedis
from unittest.mock import patch

@pytest.fixture(autouse=True)
def fake_redis():
    fake = FakeRedis(decode_responses=True)
    
    with patch("src.db.red.r", fake):
        yield fake

@pytest.fixture(autouse=True)
def set_jwt_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JWT_KEY", "testsecrettestsecrettestsecrettestsecret")
