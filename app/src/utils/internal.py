import hashlib
import hmac
import json
from os import getenv
from typing import Annotated, Any

from fastapi import Header, Request

from src.api.models.base import ErrorResponse
from src.api.models.exc import AppException
from src.enums import ErrorResponseCode

INTERNAL_SECRET_KEY = "INTERNAL_SECRET"

def verify_signature(body_bytes: bytes, signature: str):
    key = getenv(INTERNAL_SECRET_KEY)
    if key is None:
        raise ValueError("Internal secret not set.")
    expected = hmac.new(
        key.encode(),
        body_bytes,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)

async def check_internal(request: Request, x_signature: Annotated[str | None, Header()]):
    body: dict[str, Any] = await request.json()
    body_bytes = json.dumps(body, separators=(",", ":"), sort_keys=True, default=str).encode()
    if not x_signature or not verify_signature(body_bytes, x_signature):
        raise AppException(
            status_code = 403,
            error = ErrorResponse(
                code = ErrorResponseCode.INTERNAL_ERROR,
                message = ""
            )
        )
    return body