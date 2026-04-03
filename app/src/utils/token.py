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
    return jwt.encode(payload.model_dump(), get_key(), JWT_ALG), exp

def create_refresh_token(user_id: str):
    jti = str(uuid4())
    iat = datetime.now(timezone.utc)
    exp = iat + timedelta(minutes=REFRESH_TOKEN_EXPIRE)
    payload = RefreshTokenPayload(
        sub = user_id,
        jti = jti,
        iat = int(iat.timestamp()),
        exp = int(exp.timestamp())
    )
    return jwt.encode(payload.model_dump(), get_key(), JWT_ALG), exp, jti

def verify_access_token(token: str):
    try:
        payload_data = jwt.decode(token, get_key(), [JWT_ALG])
        try:
            payload = AccessTokenPayload(**payload_data)
            if payload.type != ACCESS_TOKEN_TYPE:
                return JWTTokenStatus.INVALID
        except ValidationError:
            return JWTTokenStatus.INVALID
    except jwt.exceptions.InvalidSignatureError:
        return JWTTokenStatus.INVALID
    except jwt.exceptions.ExpiredSignatureError:
        return JWTTokenStatus.EXPIRED
    return payload

def verify_refresh_token(token: str):
    try:
        payload_data = jwt.decode(token, get_key(), [JWT_ALG])
        try:
            payload = RefreshTokenPayload(**payload_data)
            if payload.type != REFRESH_TOKEN_TYPE:
                return JWTTokenStatus.INVALID
        except ValidationError:
            return JWTTokenStatus.INVALID
    except jwt.exceptions.InvalidSignatureError:
        return JWTTokenStatus.INVALID
    except jwt.exceptions.ExpiredSignatureError:
        return JWTTokenStatus.EXPIRED
    return payload