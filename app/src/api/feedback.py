from fastapi import APIRouter, Depends
from typing import Annotated
from sqlalchemy.dialects.postgresql import insert

from src.api.models.base import PromptShownData
from src.api.models.request import PromptShownRequest
from src.api.models.response import PromptShownResponse
from src.db.db import SessionDep
from src.db.models import FeedbackResponse
from src.utils.auth import check_auth
from src.utils.feedback import validate_campaign_id
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