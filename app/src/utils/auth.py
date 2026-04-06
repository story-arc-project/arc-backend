from typing import Annotated
from fastapi import Cookie
from sqlmodel import select

from src.api.models.base import ErrorResponse
from src.api.models.exc import AppException
from src.db.db import SessionDep
from src.db.models import Token
from src.enums import ErrorResponseCode, JWTTokenStatus
from src.utils.token import hash_jti, verify_access_token


err_st_c = 401
err_msg = "Login required."


def check_auth(session: SessionDep, accessToken: Annotated[str | None, Cookie()] = None):
    if accessToken is None:
        raise AppException(
            err_st_c,
            ErrorResponse(
                code = ErrorResponseCode.AUTH_MISSING_COOKIES,
                message = err_msg
            )
        )
    payload = verify_access_token(accessToken)
    if payload == JWTTokenStatus.EXPIRED:
        raise AppException(
            err_st_c,
            ErrorResponse(
                code = ErrorResponseCode.AUTH_TOKEN_EXPIRED,
                message = err_msg
            )
        )
    if payload == JWTTokenStatus.INVALID:
        raise AppException(
            err_st_c,
            ErrorResponse(
                code = ErrorResponseCode.AUTH_TOKEN_INVALID,
                message = err_msg
            )
        )
    token = session.exec(select(Token).where(Token.jti_hash == hash_jti(payload.jti))).one_or_none()
    if token is None:
        raise AppException(
            err_st_c,
            ErrorResponse(
                code = ErrorResponseCode.AUTH_TOKEN_INVALID,
                message = err_msg
            )
        )
    if token.revoked:
        raise AppException(
            403,
            ErrorResponse(
                code = ErrorResponseCode.AUTH_REVOKED,
                message = err_msg
            )
        )
    if token.next is not None:
        raise AppException(
            403,
            ErrorResponse(
                code = ErrorResponseCode.AUTH_REUSE_DETECTED,
                message = err_msg
            )
        )
    return payload