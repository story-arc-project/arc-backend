import traceback
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, Response
from sqlmodel import select
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

from src.api.models.base import ErrorResponse, ResumeData, ResumeList, ResumeListData, UUIDDataWithTitle, UUIDDataWithTitleNone
from src.api.models.exc import AppException
from src.api.models.request import ResumePatchRequest, ResumePostRequest
from src.api.models.response import DeleteSuccessResponse, PostSuccessResponse, ResumeListResponse, ResumeResponse
from src.db.db import SessionDep
from src.db.models import Experience, Resume, User, UserProfile
from src.enums import ErrorResponseCode
from src.utils.auth import check_auth
from src.utils.ratelimit import analysis_rate_limiters
from src.utils.token import AccessTokenPayload

export_router = APIRouter()

@export_router.post("/resume")
async def post_resume(
    body: ResumePostRequest,
    session: SessionDep,
    response: Response,
    payload: Annotated[AccessTokenPayload, Depends(check_auth)],
    _user_limit: Annotated[None, Depends(analysis_rate_limiters["resume"]["user"])],
    _ip_limit: Annotated[None, Depends(analysis_rate_limiters["resume"]["ip"])]
):
    statement = select(Experience).where(Experience.user_id == payload.sub)
    result = session.exec(statement).all()
    res = session.exec(select(UserProfile, User).join(User).where(UserProfile.user_id == payload.sub)).one_or_none()
    if res is None:
        raise AppException(
            404,
            ErrorResponse(
                code = ErrorResponseCode.NOT_FOUND,
                message = "User profile not found"
            )
        )
    user_profile, user = res
    sources: list[str] = []
    for experience in result:
        sources.append(str(experience.content))
    if body.title:
        title = body.title
    else:
        title = f"{datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d")} resume"
    new_resume = Resume(user_id = payload.sub, language = body.language, title = title)
    for experience in result:
        if experience.user_id != payload.sub:
            raise AppException(
                403,
                ErrorResponse(
                    code = ErrorResponseCode.RESOURCE_NOT_ALLOWED,
                    message = "Access for the resource is not allowed"
                )
        )
    try:
        req = requests.post("http://ai_analyst:8001/resume", json={
            "resume_id": str(new_resume.id),
            "sources": sources,
            "name_ko": user_profile.name,
            "email": user.email,
            "phone": user_profile.phone,
            "school": user_profile.school,
            "department": user_profile.department,
            "language": body.language
        })
        req.raise_for_status()
        new_resume.task_id = req.json()["task_id"]
        session.add(new_resume)
        session.commit()
        session.refresh(new_resume)
    except Exception:
        traceback.print_exc()
        session.rollback()
        raise AppException(
            500,
            ErrorResponse(
                code = ErrorResponseCode.SERVER_ERROR,
                message = "An error occurred while processing the request"
            )
        )
    response.status_code = 200
    return PostSuccessResponse(
        message = "Resume generation queued successfully.",
        data = UUIDDataWithTitleNone(
            id = new_resume.id,
            title = new_resume.title
        )
    )

@export_router.get("/resume")
async def get_resumes(session: SessionDep, response: Response, payload: Annotated[AccessTokenPayload, Depends(check_auth)]):
    statement = (
        select(Resume)
        .where(Resume.user_id == payload.sub)
    )
    result = session.exec(statement).all()
    response.status_code = 200
    return ResumeListResponse(
        message = "Fetch success.",
        data = ResumeList(
            count = len(result),
            contents = [ResumeListData(
                id = analysis.id,
                title = analysis.title,
                language = analysis.language,
                status = analysis.status,
                created_at = analysis.created_at,
                updated_at = analysis.updated_at
            ) for analysis in result]
        )
    )

@export_router.get("/resume/{resume_id}")
async def get_resume(resume_id: UUID, session: SessionDep, response: Response, payload: Annotated[AccessTokenPayload, Depends(check_auth)]):
    resume = session.get(Resume, resume_id)
    if resume is None:
        raise AppException(
            404,
            ErrorResponse(
                code = ErrorResponseCode.NOT_FOUND,
                message = "Resume not found"
            )
        )
    if resume.user_id != payload.sub:
        raise AppException(
            403,
            ErrorResponse(
                code = ErrorResponseCode.RESOURCE_NOT_ALLOWED,
                message = "Access for the resource is not allowed"
            )
        )
    response.status_code = 200
    return ResumeResponse(
        message = "Fetch success.",
        data = ResumeData(
            id = resume.id,
            title = resume.title,
            language = resume.language,
            status = resume.status,
            created_at = resume.created_at,
            updated_at = resume.updated_at,
            result = resume.result
        )
    )

@export_router.patch("/resume/{resume_id}")
async def patch_resume(
    resume_id: UUID,
    body: ResumePatchRequest,
    session: SessionDep,
    response: Response,
    payload: Annotated[AccessTokenPayload, Depends(check_auth)]
):
    resume = session.get(Resume, resume_id)
    if resume is None:
        raise AppException(
            404,
            ErrorResponse(
                code = ErrorResponseCode.NOT_FOUND,
                message = "Resume not found"
            )
        )
    if resume.user_id != payload.sub:
        raise AppException(
            403,
            ErrorResponse(
                code = ErrorResponseCode.RESOURCE_NOT_ALLOWED,
                message = "Access for the resource is not allowed"
            )
        )
    resume.title = body.title
    try:
        session.add(resume)
        session.commit()
        session.refresh(resume)
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
    response.status_code = 200
    return PostSuccessResponse(
        message = "Keyword analysis patch success.",
        data = UUIDDataWithTitle(
            id = resume.id,
            title = body.title
        )
    )

@export_router.delete("/resume/{resume_id}")
async def remove_bookmark(resume_id: UUID, session: SessionDep, response: Response, payload: Annotated[AccessTokenPayload, Depends(check_auth)]):
    resume = session.get(Resume, resume_id)
    if resume is None:
        raise AppException(
            404,
            ErrorResponse(
                code=ErrorResponseCode.NOT_FOUND,
                message="Resume not found"
            )
        )
    if resume.user_id != payload.sub:
        raise AppException(
            403,
            ErrorResponse(
                code = ErrorResponseCode.RESOURCE_NOT_ALLOWED,
                message = "Access for the resource is not allowed"
            )
        )
    try:
        session.delete(resume)
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
        message="Resume removed."
    )