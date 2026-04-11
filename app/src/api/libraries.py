from typing import Annotated
from fastapi import APIRouter, Depends, Response

from src.api.models.base import ErrorResponse, UUIDData
from src.api.models.exc import AppException
from src.api.models.request import LibraryPostRequest
from src.api.models.response import PostSuccessResponse
from src.db.db import SessionDep
from src.db.models import Library
from src.enums import ErrorResponseCode
from src.utils.auth import check_auth
from src.utils.token import AccessTokenPayload

libraries_router = APIRouter()

@libraries_router.post("/")
async def post_library(body: LibraryPostRequest, session: SessionDep, response: Response, payload: Annotated[AccessTokenPayload, Depends(check_auth)]):
    try:
        new_library = Library(
            user_id = payload.sub,
            name = body.name,
            color = body.color,
            icon = body.icon,
            is_system = body.is_system,
            filter = body.filter
        )
        session.add(new_library)
        session.commit()
        session.refresh(new_library)
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
        message = "New library created.",
        data = UUIDData(
            id = new_library.id
        )
    )