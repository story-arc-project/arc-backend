import traceback
from typing import Annotated
from fastapi import APIRouter, Depends, Response
from sqlmodel import select
import requests

from src.api.models.base import ErrorResponse, ResumeList, ResumeListData, UUIDData
from src.api.models.exc import AppException
from src.api.models.request import ResumePostRequest
from src.api.models.response import PostSuccessResponse, ResumeListResponse
from src.db.db import SessionDep
from src.db.models import Experience, Resume, User, UserProfile
from src.enums import ErrorResponseCode
from src.utils.auth import check_auth
from src.utils.token import AccessTokenPayload

export_router = APIRouter()

@export_router.post("/resume")
async def post_resume(body: ResumePostRequest, session: SessionDep, response: Response, payload: Annotated[AccessTokenPayload, Depends(check_auth)]):
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
    try:
        new_resume = Resume(user_id = payload.sub)
        for experience in result:
            if experience.user_id != payload.sub:
                raise AppException(
                    403,
                    ErrorResponse(
                        code = ErrorResponseCode.RESOURCE_NOT_ALLOWED,
                        message = "Access for the resource is not allowed"
                    )
                )
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
        data = UUIDData(
            id = new_resume.id
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
                created_at = analysis.created_at,
                updated_at = analysis.updated_at
            ) for analysis in result]
        )
    )