from fastapi import Cookie, status
from os import getenv
from typing import Annotated

from src.api.models.base import ErrorResponse
from src.api.models.exc import AppException
from src.const import ADMIN_PAGE_NOT_ALLOWED
from src.db.db import SessionDep
from src.db.models import User
from src.enums import ErrorResponseCode
from src.utils.auth import check_auth

def is_admin_email(email: str):
    admin_emails = getenv("ADMIN_EMAILS", "")
    admin_email_list = [e.strip() for e in admin_emails.split(",") if e.strip()]
    return email in admin_email_list

async def require_admin(session: SessionDep, accessToken: Annotated[str | None, Cookie()]):
    try:
        payload = check_auth(session, accessToken)
    except AppException:
        raise AppException(
            status.HTTP_404_NOT_FOUND,
            ErrorResponse(code=ErrorResponseCode.NOT_FOUND, message=ADMIN_PAGE_NOT_ALLOWED),
        )
    result = session.get(User, payload.sub)
    if result is None or not is_admin_email(result.email):
        raise AppException(
            status.HTTP_404_NOT_FOUND,
            ErrorResponse(code=ErrorResponseCode.NOT_FOUND, message=ADMIN_PAGE_NOT_ALLOWED),
        )
    return payload