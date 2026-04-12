from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, Response
from sqlmodel import select

from src.api.models.base import ErrorResponse, PresetResponseData, PresetsResponseData, SuccessResponseWithData
from src.api.models.exc import AppException
from src.db.db import SessionDep
from src.db.models import Preset
from src.enums import ErrorResponseCode
from src.utils.auth import check_auth
from src.utils.token import AccessTokenPayload

presets_router = APIRouter()

@presets_router.get("/")
async def get_presets(session: SessionDep, response: Response, payload: Annotated[AccessTokenPayload, Depends(check_auth)]):
    statement = select(Preset).where(Preset.user_id == payload.sub)
    result = session.exec(statement).all()
    response.status_code = 200
    return SuccessResponseWithData[PresetsResponseData](
        message = "Fetch success",
        data = PresetsResponseData(
            count = len(result),
            contents = [PresetResponseData(**obj.model_dump()) for obj in result]
        )
    )

@presets_router.get("/{preset_id}")
async def get_preset_by_id(preset_id: UUID, session: SessionDep, response: Response, payload: Annotated[AccessTokenPayload, Depends(check_auth)]):
    statement = select(Preset).where(Preset.id == preset_id)
    result = session.exec(statement).one_or_none()
    if result is None:
        raise AppException(
            404,
            ErrorResponse(
                code = ErrorResponseCode.NOT_FOUND,
                message = "Preset not found"
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
    return SuccessResponseWithData[PresetResponseData](
        message = "Fetch success",
        data = PresetResponseData(**result.model_dump())
    )