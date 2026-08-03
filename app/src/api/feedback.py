from datetime import datetime
from fastapi import APIRouter, Depends
from typing import Annotated
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import select

from src.api.models.base import FeedbackResponseData, PromptShownData
from src.api.models.request import PromptShownRequest, FeedbackResponseRequest
from src.api.models.response import FeedbackResponse as FeedbackResponseNotDBModel, PromptShownResponse
from src.db.db import SessionDep
from src.db.models import FeedbackResponse
from src.utils.auth import check_auth
from src.utils.feedback import filter_context, validate_campaign_id
from src.utils.token import AccessTokenPayload

feedback_router = APIRouter()

@feedback_router.post("/campaigns/{campaign_id}/prompt-shown")
def record_prompt_shown(
    campaign_id: Annotated[str, Depends(validate_campaign_id)],
    body: PromptShownRequest,
    session: SessionDep,
    payload: Annotated[AccessTokenPayload, Depends(check_auth)]
):
    stmt = (
        insert(FeedbackResponse)
        .values(
            user_id = payload.sub,
            campaign_id = campaign_id,
            trigger_source = body.trigger_source,
        )
        .on_conflict_do_nothing(index_elements=["user_id", "campaign_id"])
    )
    result = session.exec(stmt)
    session.commit()

    return PromptShownResponse(
        message = "prompt shown recorded",
        data = PromptShownData(
            created = result.rowcount > 0
        )
    )

@feedback_router.post("/campaigns/{campaign_id}/responses")
def record_response(
    campaign_id: str,
    body: FeedbackResponseRequest,
    session: SessionDep,
    payload: Annotated[AccessTokenPayload, Depends(check_auth)]
):
    filtered_context = filter_context(body.context)

    responded_at = datetime.now()

    row = session.exec(
        select(FeedbackResponse).where(
            FeedbackResponse.user_id == payload.sub,
            FeedbackResponse.campaign_id == campaign_id,
        )
    ).first()

    if row is None:
        row = FeedbackResponse(
            user_id=payload.sub,
            campaign_id=campaign_id,
            trigger_source=None,
        )
        session.add(row)

    row.rating = body.rating
    row.comment = body.comment
    row.context = filtered_context
    row.responded_at = responded_at

    session.commit()

    return FeedbackResponseNotDBModel(
        message="feedback response recorded",
        data=FeedbackResponseData(responded_at=responded_at),
    )