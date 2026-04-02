from unittest.mock import patch
from datetime import datetime, timedelta, timezone
from uuid import UUID

from src.utils.token import (
    create_access_token,
    create_refresh_token,
    verify_access_token,
    verify_refresh_token,
    ACCESS_TOKEN_TYPE,
    REFRESH_TOKEN_TYPE
)
from src.enums import JWTTokenStatus
from src.const import ACCESS_TOKEN_EXPIRE, REFRESH_TOKEN_EXPIRE


def test_create_and_verify_access_token():
    user_id = "123"
    token, exp = create_access_token(user_id)

    payload = verify_access_token(token)
    assert payload != JWTTokenStatus.EXPIRED
    assert payload != JWTTokenStatus.INVALID
    assert payload.sub == user_id
    assert payload.type == str(ACCESS_TOKEN_TYPE)
    assert isinstance(payload.exp, int)
    assert int(exp.timestamp()) == payload.exp


def test_create_and_verify_refresh_token():
    user_id = "456"
    token, exp, jti = create_refresh_token(user_id)

    assert isinstance(UUID(jti), UUID)
    payload = verify_refresh_token(token)
    assert payload != JWTTokenStatus.EXPIRED
    assert payload != JWTTokenStatus.INVALID
    assert payload.sub == user_id
    assert payload.jti == jti
    assert payload.type == str(REFRESH_TOKEN_TYPE)
    assert isinstance(payload.exp, int)
    assert int(exp.timestamp()) == payload.exp


def test_access_token_expired():
    user_id = "789"
    
    past_time = datetime.now(timezone.utc) - timedelta(minutes=ACCESS_TOKEN_EXPIRE + 1)
    with patch("src.utils.token.datetime") as mock_dt:
        mock_dt.now.return_value = past_time
        mock_dt.now.timezone = timezone.utc
        token, _ = create_access_token(user_id)
    
    result = verify_access_token(token)
    assert result == JWTTokenStatus.EXPIRED


def test_refresh_token_expired():
    user_id = "101"
    past_time = datetime.now(timezone.utc) - timedelta(minutes=REFRESH_TOKEN_EXPIRE + 1)
    
    with patch("src.utils.token.datetime") as mock_dt:
        mock_dt.now.return_value = past_time
        mock_dt.now.timezone = timezone.utc
        token, exp, _ = create_refresh_token(user_id)
    
    result = verify_refresh_token(token)
    assert result == JWTTokenStatus.EXPIRED


def test_invalid_access_token_type():
    user_id = "202"
    token = create_refresh_token(user_id)[0]
    result = verify_access_token(token)
    assert result == JWTTokenStatus.INVALID


def test_invalid_refresh_token_type():
    user_id = "303"
    token, _ = create_access_token(user_id)
    result = verify_refresh_token(token)
    assert result == JWTTokenStatus.INVALID


def test_invalid_token_signature():
    user_id = "404"
    token, _ = create_access_token(user_id)
    
    tampered_token = token + "a"
    result = verify_access_token(tampered_token)
    assert result == JWTTokenStatus.INVALID