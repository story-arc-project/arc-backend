from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Response
from sqlmodel import col, select
from typing import Annotated

from src.api.models.base import CreditData, CreditTransactionData
from src.api.models.response import CreditAccountResponse, CreditTransactionListResponse
from src.const import PACKAGES
from src.db.db import SessionDep
from src.db.models import CreditLedger, UserCreditAccount
from src.utils.auth import check_auth
from src.utils.token import AccessTokenPayload

credits_router = APIRouter()

@credits_router.get("/packages")
def get_credit_packages(
    response: Response,
):
    response.headers["Cache-Control"] = "no-store"
    return {"packages": PACKAGES}

@credits_router.get("")
def get_credit_account(
    session: SessionDep,
    response: Response,
    payload: Annotated[AccessTokenPayload, Depends(check_auth)],
):
    response.headers["Cache-Control"] = "private, no-store"
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

@credits_router.get("/transactions")
def get_credit_transactions(
    session: SessionDep,
    response: Response,
    payload: Annotated[AccessTokenPayload, Depends(check_auth)],
):
    response.headers["Cache-Control"] = "private, no-store"
    result = session.exec(
        select(CreditLedger)
        .where(CreditLedger.user_id == payload.sub)
        .order_by(col(CreditLedger.created_at).desc())
    ).all()
    return CreditTransactionListResponse(
        message="User credit transactions fetched successfully",
        data=[
            CreditTransactionData(
                id=transaction.id,
                amount=transaction.amount,
                reason=transaction.reason,
                feature=transaction.feature,
                reference_type=transaction.reference_type,
                reference_id=transaction.reference_id,
                balance_after=transaction.balance_after,
                created_at=transaction.created_at
            ) for transaction in result
        ]
    )