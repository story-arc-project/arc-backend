from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlmodel import and_, col, or_, select
from typing import Annotated, Optional

from src.api.models.base import CreditData, CreditTransactionData, NextCursor
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
    cursor_created_at: Optional[datetime] = Query(default=None),
    cursor_id: Optional[UUID] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
):
    response.headers["Cache-Control"] = "private, no-store"

    query = select(CreditLedger).where(CreditLedger.user_id == payload.sub)

    if cursor_created_at is not None and cursor_id is not None:
        query = query.where(
            or_(
                CreditLedger.created_at < cursor_created_at,
                and_(
                    CreditLedger.created_at == cursor_created_at,
                    CreditLedger.id < cursor_id,
                ),
            )
        )

    items = session.exec(
        query.order_by(
            col(CreditLedger.created_at).desc(),
            col(CreditLedger.id).desc(),
        ).limit(limit + 1)
    ).all()

    has_more = len(items) > limit
    records = items[:limit]

    next_cursor = None
    if has_more and records:
        last = records[-1]
        next_cursor = NextCursor(
            created_at=last.created_at,
            id=last.id
        )

    return CreditTransactionListResponse(
        message="User credit transactions fetched successfully",
        data=[
            CreditTransactionData(
                id=t.id,
                amount=t.amount,
                reason=t.reason,
                feature=t.feature,
                reference_type=t.reference_type,
                reference_id=t.reference_id,
                balance_after=t.balance_after,
                created_at=t.created_at,
            )
            for t in records
        ],
        has_more=has_more,
        next_cursor=next_cursor,
    )