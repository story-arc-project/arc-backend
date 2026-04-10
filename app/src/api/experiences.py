from typing import Annotated
from fastapi import APIRouter, Depends, Response

from src.api.models.base import ErrorResponse, UUIDData
from src.api.models.exc import AppException
from src.api.models.request import ExperiencePostRequest
from src.api.models.response import PostSuccessResponse
from src.db.db import SessionDep
from src.db.models import Experience
from src.enums import ErrorResponseCode
from src.utils.auth import check_auth
from src.utils.token import AccessTokenPayload

experiences_router = APIRouter()

@experiences_router.post("/")
async def post_experience(body: ExperiencePostRequest, session: SessionDep, response: Response, payload: Annotated[AccessTokenPayload, Depends(dependency=check_auth)]):
    try:
        new_experience = Experience(
            user_id = payload.sub,
            type = body.type,
            content = body.content
        )
        session.add(new_experience)
        session.commit()
        session.refresh(new_experience)
    except:
        session.rollback()
        raise AppException(
            500,
            ErrorResponse(
                code=ErrorResponseCode.SERVER_ERROR,
                message="Server side error."
            )
        )
    response.status_code = 201
    return PostSuccessResponse(
        message = "New experience created.",
        data = UUIDData(
            id = new_experience.id
        )
    )