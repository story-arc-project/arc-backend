from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlmodel import select
from typing import Annotated

from src.api.models.base import CreditData
from src.api.models.response import CreditAccountResponse
from src.const import PACKAGES
from src.db.db import SessionDep
from src.db.models import UserCreditAccount
from src.utils.auth import check_auth
from src.utils.token import AccessTokenPayload

credits_router = APIRouter()

@credits_router.get("/packages")
def get_credit_packages():
    return {"packages": PACKAGES}

@credits_router.get("")
def get_credit_account(
    session: SessionDep,
    payload: Annotated[AccessTokenPayload, Depends(check_auth)],
):
    account = session.exec(
        select(UserCreditAccount).where(UserCreditAccount.user_id == payload.sub)
    ).one_or_none()
    if account is None:
        return CreditAccountResponse(
            message="User credit account not found",
            data=CreditData(
                balance=0,
                reserved=0,
                available=0,
                updated_at=datetime.now(timezone.utc)
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