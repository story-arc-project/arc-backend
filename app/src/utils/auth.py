from typing import Annotated
from fastapi import Cookie


from src.api.models.base import ErrorResponse
from src.api.models.exc import AppException
from src.enums import ErrorResponseCode, JWTTokenStatus
from src.utils.token import verify_access_token


err_st_c = 401
err_msg = "Login required."


def check_auth(accessToken: Annotated[str | None, Cookie()] = None):
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
    try:
        _ = int(payload.sub)
    except ValueError:
        raise AppException(
            err_st_c,
            ErrorResponse(
                code = ErrorResponseCode.AUTH_TOKEN_INVALID,
                message = err_msg
            )
        )
    return payload