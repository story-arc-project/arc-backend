import traceback
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, Response
from sqlmodel import col, select
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

from src.api.models.base import ErrorResponse, ResumeData, ResumeList, ResumeListData, UUIDData, UUIDDataWithTitleNone
from src.api.models.exc import AppException
from src.api.models.request import CoverLetterPostRequest, ResumePatchRequest, ResumePostRequest
from src.api.models.response import DeleteSuccessResponse, PostSuccessResponse, ResumeListResponse, ResumeResponse
from src.db.db import SessionDep
from src.db.models import CoverLetter, Experience, Resume, User, UserProfile
from src.enums import AnalysisStatus, ErrorResponseCode
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
    if body.experience_ids is None:
        statement = select(Experience).where(Experience.user_id == payload.sub)
        result = session.exec(statement).all()
    else:
        statement = select(Experience).where(col(Experience.id).in_(body.experience_ids))
        result = session.exec(statement).all()
        if len(result) != len(set(body.experience_ids)):
            raise AppException(
                404,
                ErrorResponse(
                    code = ErrorResponseCode.NOT_FOUND,
                    message = "One or more experiences not found"
                )
            )
    sources: list[str] = []
    for experience in result:
        if experience.user_id != payload.sub:
            raise AppException(
                403,
                ErrorResponse(
                    code = ErrorResponseCode.RESOURCE_NOT_ALLOWED,
                    message = "Access for the resource is not allowed"
                )
        )
        sources.append(str(experience.content))
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
    if body.title:
        title = body.title
    else:
        title = f"{datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d")} resume"
    new_resume = Resume(user_id = payload.sub, language = body.language, title = title, experience_ids = body.experience_ids)
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
            experience_ids = resume.experience_ids,
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
    if resume.status != AnalysisStatus.SUCCESS or resume.result is None:
        raise AppException(
            400,
            ErrorResponse(
                code = ErrorResponseCode.BAD_REQUEST,
                message = "Resume is not completed yet."
            )
        )
    if body.title is not None:
        resume.title = body.title
    if body.result is not None:
        new_result = dict(body.result)
        schema_version = resume.result.get("schema_version")
        if schema_version is not None:
            new_result["schema_version"] = schema_version
        resume.result = new_result
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
    return ResumeResponse(
        message = "Resume patch success.",
        data = ResumeData(
            id = resume.id,
            title = resume.title,
            language = resume.language,
            status = resume.status,
            experience_ids = resume.experience_ids,
            created_at = resume.created_at,
            updated_at = resume.updated_at,
            result = resume.result
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
        traceback.print_exc()
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

@export_router.post("/cover_letter")
async def post_cover_letter(
    body: CoverLetterPostRequest,
    session: SessionDep,
    response: Response,
    payload: Annotated[AccessTokenPayload, Depends(check_auth)],
    _user_limit: Annotated[None, Depends(analysis_rate_limiters["cover_letter"]["user"])],
    _ip_limit: Annotated[None, Depends(analysis_rate_limiters["cover_letter"]["ip"])]
):
    if body.experience_ids is None:
        statement = select(Experience).where(Experience.user_id == payload.sub)
        result = session.exec(statement).all()
    else:
        statement = select(Experience).where(col(Experience.id).in_(body.experience_ids))
        result = session.exec(statement).all()
        if len(result) != len(set(body.experience_ids)):
            raise AppException(
                404,
                ErrorResponse(
                    code = ErrorResponseCode.NOT_FOUND,
                    message = "One or more experiences not found"
                )
            )
    sources: list[dict] = []
    for experience in result:
        if experience.user_id != payload.sub:
            raise AppException(
                403,
                ErrorResponse(
                    code = ErrorResponseCode.RESOURCE_NOT_ALLOWED,
                    message = "Access for the resource is not allowed"
                )
        )
        sources.append(experience.content)
    user_profile = session.exec(select(UserProfile).where(UserProfile.user_id == payload.sub)).one_or_none()
    if user_profile is None:
        raise AppException(
            404,
            ErrorResponse(
                code = ErrorResponseCode.NOT_FOUND,
                message = "User profile not found"
            )
        )
    new_cover_letter = CoverLetter(
        user_id = payload.sub,
        target_company = body.target_company,
        target_job = body.target_job,
        job_key = body.job_key,
        region = body.region,
        questions = body.questions,
        experience_ids = body.experience_ids
    )
    try:
        req = requests.post("http://ai_analyst:8001/cover_letter", json={
            "cover_letter_id": str(new_cover_letter.id),
            "experiences": sources,
            "name": user_profile.name,
            "target_company": body.target_company,
            "target_job": body.target_job,
            "school": user_profile.school,
            "department": user_profile.department,
            "motivation": body.motivation,
            "career_goal": body.career_goal,
            "extra_notes": body.extra_notes,
            "questions": body.questions,
        })
        req.raise_for_status()
        new_cover_letter.task_id = req.json()["task_id"]
        session.add(new_cover_letter)
        session.commit()
        session.refresh(new_cover_letter)
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
        message = "Cover letter generation queued successfully.",
        data = UUIDData(
            id = new_cover_letter.id
        )
    )