from copy import deepcopy
import json
import traceback
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, Response
from sqlmodel import select
import requests

from src.api.models.base import ErrorResponse, ExperienceResponseData, ExperiencesResponseData, SuccessResponseWithData, UUIDData
from src.api.models.exc import AppException
from src.api.models.request import ExperiencePatchRequest, ExperiencePostRequest, ExperiencePutRequest
from src.api.models.response import DeleteSuccessResponse, PostSuccessResponse, PutSuccessResponse
from src.db.db import SessionDep
from src.db.models import Experience, IndividualAnalysis
from src.enums import ErrorResponseCode
from src.utils.auth import check_auth
from src.utils.ratelimit import analysis_rate_limiters
from src.utils.token import AccessTokenPayload

experiences_router = APIRouter()

@experiences_router.post("/")
async def post_experience(
    body: ExperiencePostRequest,
    session: SessionDep,
    response: Response,
    payload: Annotated[AccessTokenPayload, Depends(check_auth)],
    _user_limit: Annotated[None, Depends(analysis_rate_limiters["individual"]["user"])],
    _ip_limit: Annotated[None, Depends(analysis_rate_limiters["individual"]["ip"])]
):
    try:
        new_experience = Experience(
            user_id = payload.sub,
            type = body.type,
            importance = body.importance,
            content = body.content
        )
        new_individual_analysis = IndividualAnalysis(
            user_id=payload.sub,
            experience_id = new_experience.id
        )
        req = requests.post("http://ai_analyst:8001/individual", json={
            "analysis_id": str(new_individual_analysis.id),
            "input": [json.dumps(body.content)]
        })
        req.raise_for_status()
        new_individual_analysis.task_id = req.json()["task_id"]
        session.add(new_experience)
        session.add(new_individual_analysis)
        session.commit()
        session.refresh(new_experience)
    except Exception:
        traceback.print_exc()
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

@experiences_router.get("/")
async def get_experience(session: SessionDep, response: Response, payload: Annotated[AccessTokenPayload, Depends(check_auth)]):
    statement = select(Experience).where(Experience.user_id == payload.sub)
    result = session.exec(statement).all()
    response.status_code = 200
    return SuccessResponseWithData[ExperiencesResponseData](
        message = "Fetch success",
        data = ExperiencesResponseData(
            count = len(result),
            contents = [ExperienceResponseData(**obj.model_dump()) for obj in result]
        )
    )

@experiences_router.get("/{experience_id}")
async def get_experience_by_id(experience_id: UUID, session: SessionDep, response: Response, payload: Annotated[AccessTokenPayload, Depends(check_auth)]):
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
        data = ExperienceResponseData(**result.model_dump())
    )

@experiences_router.put("/{experience_id}")
async def put_experience_by_id(body: ExperiencePutRequest, experience_id: UUID, session: SessionDep, response: Response, payload: Annotated[AccessTokenPayload, Depends(check_auth)]):
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
    try:
        result.content = body.content
        result.importance = body.importance
        session.add(result)
        session.commit()
        session.refresh(result)
    except:
        session.rollback()
        raise AppException(
            500,
            ErrorResponse(
                code=ErrorResponseCode.SERVER_ERROR,
                message="Server side error."
            )
        )
    response.status_code = 200
    return PutSuccessResponse(
        message = "Experience edit success."
    )

@experiences_router.patch("/{experience_id}/importance")
async def patch_experience_importance(body: ExperiencePatchRequest, experience_id: UUID, session: SessionDep, response: Response, payload: Annotated[AccessTokenPayload, Depends(check_auth)]):
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
    try:
        result.importance = body.importance
        session.add(result)
        session.commit()
        session.refresh(result)
    except:
        session.rollback()
        raise AppException(
            500,
            ErrorResponse(
                code=ErrorResponseCode.SERVER_ERROR,
                message="Server side error."
            )
        )
    response.status_code = 200
    return PutSuccessResponse(
        message = "Experience importance patch success."
    )

@experiences_router.delete("/{experience_id}")
async def delete_experience_by_id(experience_id: UUID, session: SessionDep, response: Response, payload: Annotated[AccessTokenPayload, Depends(check_auth)]):
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
    try:
        session.delete(result)
        session.commit()
    except:
        session.rollback()
        raise AppException(
            500,
            ErrorResponse(
                code=ErrorResponseCode.SERVER_ERROR,
                message="Server side error."
            )
        )
    response.status_code = 204
    return DeleteSuccessResponse(
        message = "Experience deleted."
    )

@experiences_router.post("/{experience_id}/duplicate")
async def duplicate_experience_by_id(experience_id: UUID, session: SessionDep, response: Response, payload: Annotated[AccessTokenPayload, Depends(check_auth)]):
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
    try:
        new = Experience(
            user_id = result.user_id,
            type = result.type,
            importance = result.importance,
            content = deepcopy(result.content)
        )
        session.add(new)
        session.commit()
        session.refresh(new)
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
        message = "Experience duplicated.",
        data = UUIDData(
            id = new.id
        )
    )