from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, Response
from sqlmodel import select

from src.api.models.base import ErrorResponse, ExperienceResponseData, SuccessResponseWithData, UUIDData
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

@experiences_router.get("/{experience_id}")
async def get_experience_by_id(experience_id: UUID, session: SessionDep, response: Response, payload: Annotated[AccessTokenPayload, Depends(dependency=check_auth)]):
    statement = select(Experience).where(Experience.id == experience_id)
    result = session.exec(statement).one_or_none()
    if result is None:
        raise AppException(
            404,
            ErrorResponse(
                code = ErrorResponseCode.NOT_FOUND,
                message = "Experience not found"
            )
        )
    if result.user_id != payload.sub:
        raise AppException(
            403,
            ErrorResponse(
                code = ErrorResponseCode.RESOURCE_NOT_ALLOWED,
                message = "Access for the resource is not allowed"
            )
        )
    response.status_code = 200
    return SuccessResponseWithData[ExperienceResponseData](
        message = "Fetch success",
        data = ExperienceResponseData(
            id = result.id,
            user_id = result.user_id,
            type = result.type,
            priority = result.priority,
            content = result.content,
            created_at = result.created_at,
            updated_at = result.updated_at
        )
    )