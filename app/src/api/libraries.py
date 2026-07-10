from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, Response
from sqlmodel import select

from src.api.models.base import ErrorResponse, ExperienceResponseData, ExperiencesResponseData, LibrariesResponseData, LibraryContentData, LibraryResponseData, SuccessResponse, SuccessResponseWithData, UUIDData
from src.api.models.exc import AppException
from src.api.models.request import LibraryPatchRequest, LibraryPostRequest
from src.api.models.response import DeleteSuccessResponse, PostSuccessResponse
from src.db.db import SessionDep
from src.db.models import Experience, Library, LibraryExperienceRelation
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

@libraries_router.get("/")
async def get_libraries(session: SessionDep, response: Response, payload: Annotated[AccessTokenPayload, Depends(check_auth)]):
    statement = select(Library).where(Library.user_id == payload.sub)
    result = session.exec(statement).all()
    response.status_code = 200
    return SuccessResponseWithData[LibrariesResponseData](
        message = "Fetch success",
        data = LibrariesResponseData(
            count = len(result),
            contents = LibraryContentData(
                system = [LibraryResponseData(**obj.model_dump()) for obj in result if obj.is_system],
                custom = [LibraryResponseData(**obj.model_dump()) for obj in result if not obj.is_system]
            )
        )
    )

@libraries_router.post("/{library_id}/experiences/{experience_id}")
async def post_library_experience(library_id: UUID, experience_id: UUID, session: SessionDep, response: Response, payload: Annotated[AccessTokenPayload, Depends(check_auth)]):
    library = session.exec(select(Library).where(Library.id == library_id)).one_or_none()
    experience = session.exec(select(Experience).where(Experience.id == experience_id)).one_or_none()
    if library is None:
        raise AppException(
            404,
            ErrorResponse(
                code = ErrorResponseCode.NOT_FOUND,
                message = "Library not found"
            )
        )
    if experience is None:
        raise AppException(
            404,
            ErrorResponse(
                code = ErrorResponseCode.NOT_FOUND,
                message = "Experience not found"
            )
        )
    if library.user_id != payload.sub or experience.user_id != payload.sub:
        raise AppException(
            403,
            ErrorResponse(
                code = ErrorResponseCode.RESOURCE_NOT_ALLOWED,
                message = "Access for the resource is not allowed"
            )
        )
    if library.is_system:
        raise AppException(
            400,
            ErrorResponse(
                code = ErrorResponseCode.BAD_REQUEST,
                message = "System library cannot have experiences."
            )
        )
    if library.filter is not None:
        raise AppException(
            400,
            ErrorResponse(
                code = ErrorResponseCode.BAD_REQUEST,
                message = "Smart library cannot have experiences."
            )
        )
    try:
        relation = LibraryExperienceRelation(
            user_id = payload.sub,
            library_id = library.id,
            experience_id = experience_id
        )
        session.add(relation)
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
    response.status_code = 201
    return SuccessResponse(
        message = "Library-Experience relation created."
    )

@libraries_router.delete("/{library_id}/experiences/{experience_id}")
async def delete_library_experience(library_id: UUID, experience_id: UUID, session: SessionDep, response: Response, payload: Annotated[AccessTokenPayload, Depends(check_auth)]):
    relation = session.exec(select(LibraryExperienceRelation).where(LibraryExperienceRelation.library_id == library_id, LibraryExperienceRelation.experience_id == experience_id)).one_or_none()
    if relation is None:
        raise AppException(
            404,
            ErrorResponse(
                code = ErrorResponseCode.NOT_FOUND,
                message = "Relation not found"
            )
        )
    if relation.user_id != payload.sub:
        raise AppException(
            403,
            ErrorResponse(
                code = ErrorResponseCode.RESOURCE_NOT_ALLOWED,
                message = "Access for the resource is not allowed"
            )
        )
    try:
        session.delete(relation)
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
        message = "Relation deleted."
    )

@libraries_router.get("/{library_id}/experiences")
async def get_library_experiences(library_id: UUID, session: SessionDep, response: Response, payload: Annotated[AccessTokenPayload, Depends(check_auth)]):
    library = session.get(Library, library_id)
    if library is None:
        raise AppException(
            404,
            ErrorResponse(
                code = ErrorResponseCode.NOT_FOUND,
                message = "Library not found"
            )
        )
    if library.user_id != payload.sub:
        raise AppException(
            403,
            ErrorResponse(
                code = ErrorResponseCode.RESOURCE_NOT_ALLOWED,
                message = "Access for the resource is not allowed"
            )
        )
    experiences = session.exec(
        select(Experience)
        .join(LibraryExperienceRelation)
        .where(LibraryExperienceRelation.library_id == library_id)
    ).all()
    response.status_code = 200
    return SuccessResponseWithData[ExperiencesResponseData](
        message = "Fetch success",
        data = ExperiencesResponseData(
            count = len(experiences),
            contents = [ExperienceResponseData(**obj.model_dump()) for obj in experiences]
        )
    )

@libraries_router.delete("/{library_id}")
async def delete_library_by_id(library_id: UUID, session: SessionDep, response: Response, payload: Annotated[AccessTokenPayload, Depends(check_auth)]):
    statement = select(Library).where(Library.id == library_id)
    result = session.exec(statement).one_or_none()
    if result is None:
        raise AppException(
            404,
            ErrorResponse(
                code = ErrorResponseCode.NOT_FOUND,
                message = "Library not found"
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
        message = "Library deleted."
    )

@libraries_router.patch("/{library_id}")
async def patch_library_by_id(library_id: UUID, body: LibraryPatchRequest, session: SessionDep, response: Response, payload: Annotated[AccessTokenPayload, Depends(check_auth)]):
    library = session.exec(select(Library).where(Library.id == library_id)).one_or_none()
    if library is None:
        raise AppException(
            404,
            ErrorResponse(
                code = ErrorResponseCode.NOT_FOUND,
                message = "Library not found"
            )
        )
    if library.user_id != payload.sub:
        raise AppException(
            403,
            ErrorResponse(
                code = ErrorResponseCode.RESOURCE_NOT_ALLOWED,
                message = "Access for the resource is not allowed"
            )
        )
    if library.is_system:
        raise AppException(
            400,
            ErrorResponse(
                code = ErrorResponseCode.BAD_REQUEST,
                message = "System library cannot be modified."
            )
        )

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(library, key, value)

    try:
        session.add(library)
        session.commit()
        session.refresh(library)
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
    return SuccessResponseWithData[LibraryResponseData](
        message = "Library updated.",
        data = LibraryResponseData(**library.model_dump())
    )