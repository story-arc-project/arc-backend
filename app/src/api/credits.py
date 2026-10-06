from fastapi import APIRouter, Depends
from sqlmodel import select
from typing import Annotated

from src.api.models.base import CreditData, ErrorResponse
from src.api.models.exc import AppException
from src.api.models.response import CreditAccountResponse
from src.const import PACKAGES
from src.db.db import SessionDep
from src.db.models import UserCreditAccount
from src.enums import ErrorResponseCode
from src.utils.auth import check_auth
from src.utils.token import AccessTokenPayload

credits_router = APIRouter()

@credits_router.get("/packages")
def get_credit_packages():
    return {"packages": PACKAGES}

@credits_router.get("/")
def get_credit_account(
    session: SessionDep,
    payload: Annotated[AccessTokenPayload, Depends(check_auth)],
):
    account = session.exec(
        select(UserCreditAccount).where(UserCreditAccount.user_id == payload.sub)
    ).one_or_none()
    if account is None:
        raise AppException(
            status_code=404,
            error=ErrorResponse(
                code=ErrorResponseCode.NOT_FOUND,
                message="User credit account not found"
            )
        )
    return CreditAccountResponse(
        message="User credit account fetched successfully",
        data=CreditData(
            balance=account.balance,
            reserved=account.reserved,
            available=account.balance - account.reserved,
            updated_at=account.updated_at
        )
    )