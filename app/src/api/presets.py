from typing import Annotated
from fastapi import APIRouter, Depends, Response
from sqlmodel import select

from src.api.models.base import PresetResponseData, PresetsResponseData, SuccessResponseWithData
from src.db.db import SessionDep
from src.db.models import Preset
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