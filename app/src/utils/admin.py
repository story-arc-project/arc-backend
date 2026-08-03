from fastapi import Cookie, Request, status
from os import getenv
from typing import Annotated
from uuid import UUID

from src.api.models.base import ErrorResponse
from src.api.models.exc import AppException
from src.const import ADMIN_PAGE_NOT_ALLOWED
from src.db.db import SessionDep, session_scope
from src.db.models import AuditLog, User
from src.enums import AuditAction, ErrorResponseCode
from src.utils.auth import check_auth
from src.utils.req import get_ip, get_user_agent
from src.utils.token import AccessTokenPayload

def is_admin_email(email: str):
    admin_emails = getenv("ADMIN_EMAILS", "")
    admin_email_list = [e.strip() for e in admin_emails.split(",") if e.strip()]
    return email in admin_email_list

async def require_admin(session: SessionDep, accessToken: Annotated[str | None, Cookie()] = None):
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

def log_audit(action: AuditAction, payload: AccessTokenPayload, target_user_id: UUID, request: Request):
    with session_scope() as audit_session:
        new_audit_log = AuditLog(
            actor_id = payload.sub,
            action = action,
            target_user_id = target_user_id,
            ip_address = get_ip(request),
            user_agent = get_user_agent(request)
        )
        audit_session.add(new_audit_log)
        try:
            audit_session.commit()
        except Exception as e:
            audit_session.rollback()
            raise AppException(
                500,
                ErrorResponse(code=ErrorResponseCode.SERVER_ERROR, message="audit log write failed")
            ) from e