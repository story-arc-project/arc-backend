import hashlib
import hmac
from typing import Literal
import jwt
from os import getenv
from uuid import uuid4
from pydantic import BaseModel, ValidationError
from datetime import datetime, timedelta, timezone
from src.const import ACCESS_TOKEN_EXPIRE, REFRESH_TOKEN_EXPIRE, JWT_ALG
from src.enums import JWTTokenStatus

ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"

class AccessTokenPayload(BaseModel):
    sub: str
    exp: int
    iat: int
    type: Literal["access"] = ACCESS_TOKEN_TYPE

class RefreshTokenPayload(BaseModel):
    sub: str
    jti: str
    exp: int
    iat: int
    type: Literal["refresh"] = REFRESH_TOKEN_TYPE

class AccessTokenResult(BaseModel):
    token: str
    exp: datetime

class RefreshTokenResult(BaseModel):
    token: str
    exp: datetime
    jti: str
    iat: datetime

def get_key():
    key = getenv("JWT_KEY")
    if key is None:
        raise RuntimeError("JWT key not found in env")
    return key

def create_access_token(user_id: str):
    iat = datetime.now(timezone.utc)
    exp = iat + timedelta(minutes=ACCESS_TOKEN_EXPIRE)
    payload = AccessTokenPayload(
        sub = user_id,
        iat = int(iat.timestamp()),
        exp = int(exp.timestamp())
    )
    return AccessTokenResult(
        token = jwt.encode(payload.model_dump(), get_key(), JWT_ALG),
        exp = exp
    )

def create_refresh_token(user_id: str):
    jti = str(uuid4())
    iat = datetime.now(timezone.utc)
    exp = iat + timedelta(days=REFRESH_TOKEN_EXPIRE)
    payload = RefreshTokenPayload(
        sub = user_id,
        jti = jti,
        iat = int(iat.timestamp()),
        exp = int(exp.timestamp())
    )
    return RefreshTokenResult(
        token = jwt.encode(payload.model_dump(), get_key(), JWT_ALG),
        exp = exp,
        jti = jti,
        iat = iat
    )

def verify_access_token(token: str):
    try:
        payload_data = jwt.decode(token, get_key(), [JWT_ALG])
        try:
            payload = AccessTokenPayload(**payload_data)
            if payload.type != ACCESS_TOKEN_TYPE:
                return JWTTokenStatus.INVALID
        except ValidationError:
            return JWTTokenStatus.INVALID
    except jwt.exceptions.DecodeError:
        return JWTTokenStatus.INVALID
    except jwt.exceptions.ExpiredSignatureError:
        return JWTTokenStatus.EXPIRED
    try:
        _ = int(payload.sub)
        return payload
    except ValueError:
        return JWTTokenStatus.INVALID

def verify_refresh_token(token: str):
    try:
        payload_data = jwt.decode(token, get_key(), [JWT_ALG])
        try:
            payload = RefreshTokenPayload(**payload_data)
            if payload.type != REFRESH_TOKEN_TYPE:
                return JWTTokenStatus.INVALID
        except ValidationError:
            return JWTTokenStatus.INVALID
    except jwt.exceptions.DecodeError:
        return JWTTokenStatus.INVALID
    except jwt.exceptions.ExpiredSignatureError:
        return JWTTokenStatus.EXPIRED
    return payload

def hash_jti(jti: str):
    key = getenv("HMAC_KEY")
    if key is None:
        raise ValueError("Hmac key not configured")
    return hmac.new(key.encode(), jti.encode(), hashlib.sha256).hexdigest()