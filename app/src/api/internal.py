from sqlmodel import select
from typing import Annotated
from fastapi import APIRouter, Depends, Response

from src.api.models.base import ErrorResponse
from src.api.models.exc import AppException
from src.api.models.request import InternalRequestFailure, InternalRequestSuccess
from src.db.db import SessionDep
from src.db.models import ComprehensiveAnalysis, CoverLetter, IndividualAnalysis, KeywordAnalysis, Resume
from src.enums import AnalysisStatus, ErrorResponseCode
from src.utils.internal import check_internal

internal_router = APIRouter()

@internal_router.post("/{analysis_type}/failure")
async def fail_individual(analysis_type: str, body: Annotated[dict, Depends(check_internal)], session: SessionDep, response: Response):
    body_validated = InternalRequestFailure.model_validate(body)
    if analysis_type == "individual":
        statement = select(IndividualAnalysis).where(IndividualAnalysis.id == body_validated.analysis_id)
    elif analysis_type == "comprehensive":
        statement = select(ComprehensiveAnalysis).where(ComprehensiveAnalysis.id == body_validated.analysis_id)
    elif analysis_type == "keyword":
        statement = select(KeywordAnalysis).where(KeywordAnalysis.id == body_validated.analysis_id)
    elif analysis_type == "resume":
        statement = select(Resume).where(Resume.id == body_validated.analysis_id)
    elif analysis_type == "cover_letter":
        statement = select(CoverLetter).where(CoverLetter.id == body_validated.analysis_id)
    else:
        raise AppException(
            status_code = 400,
            error = ErrorResponse(
                code = ErrorResponseCode.BAD_REQUEST,
                message = "Wrong analysis type."
            )
        )
    analysis = session.exec(statement).one_or_none()
    if analysis is None:
        raise AppException(
            status_code = 404,
            error = ErrorResponse(
                code = ErrorResponseCode.NOT_FOUND,
                message = ""
            )
        )
    analysis.status = AnalysisStatus.FAILED
    session.add(analysis)
    session.commit()
    response.status_code = 200
    return {}

def success_model_validate(body: dict):
    try:
        return InternalRequestSuccess.model_validate(body)
    except:
        raise AppException(
            status_code = 400,
            error = ErrorResponse(
                code = ErrorResponseCode.BAD_REQUEST,
                message = "body validation error"
            )
        )

@internal_router.post("/individual/success")
async def success_individual(body: Annotated[dict, Depends(check_internal)], session: SessionDep, response: Response):
    body_validated = success_model_validate(body)
    statement = select(IndividualAnalysis).where(IndividualAnalysis.id == body_validated.analysis_id)
    analysis = session.exec(statement).one_or_none()
    if analysis is None:
        raise AppException(
            status_code = 404,
            error = ErrorResponse(
                code = ErrorResponseCode.NOT_FOUND,
                message = ""
            )
        )
    if body_validated.vector is None:
        raise AppException(
            status_code = 400,
            error = ErrorResponse(
                code = ErrorResponseCode.BAD_REQUEST,
                message = ""
            )
        )
    analysis.vector = body_validated.vector
    analysis.result = body_validated.result
    analysis.status = AnalysisStatus.SUCCESS
    session.add(analysis)
    session.commit()
    response.status_code = 200
    return {}

@internal_router.post("/comprehensive/success")
async def success_comprehensive(body: Annotated[dict, Depends(check_internal)], session: SessionDep, response: Response):
    body_validated = success_model_validate(body)
    statement = select(ComprehensiveAnalysis).where(ComprehensiveAnalysis.id == body_validated.analysis_id)
    analysis = session.exec(statement).one_or_none()
    if analysis is None:
        raise AppException(
            status_code = 404,
            error = ErrorResponse(
                code = ErrorResponseCode.NOT_FOUND,
                message = ""
            )
        )
    if body_validated.vector is None:
        raise AppException(
            status_code = 400,
            error = ErrorResponse(
                code = ErrorResponseCode.BAD_REQUEST,
                message = ""
            )
        )
    analysis.vector = body_validated.vector
    analysis.result = body_validated.result
    analysis.status = AnalysisStatus.SUCCESS
    session.add(analysis)
    session.commit()
    response.status_code = 200
    return {}

@internal_router.post("/keyword/success")
async def success_keyword(body: Annotated[dict, Depends(check_internal)], session: SessionDep, response: Response):
    body_validated = success_model_validate(body)
    statement = select(KeywordAnalysis).where(KeywordAnalysis.id == body_validated.analysis_id)
    analysis = session.exec(statement).one_or_none()
    if analysis is None:
        raise AppException(
            status_code = 404,
            error = ErrorResponse(
                code = ErrorResponseCode.NOT_FOUND,
                message = ""
            )
        )
    analysis.result = body_validated.result
    analysis.status = AnalysisStatus.SUCCESS
    session.add(analysis)
    session.commit()
    response.status_code = 200
    return {}

@internal_router.post("/resume/success")
async def success_resume(body: Annotated[dict, Depends(check_internal)], session: SessionDep, response: Response):
    body_validated = success_model_validate(body)
    statement = select(Resume).where(Resume.id == body_validated.analysis_id)
    resume = session.exec(statement).one_or_none()
    if resume is None:
        raise AppException(
            status_code = 404,
            error = ErrorResponse(
                code = ErrorResponseCode.NOT_FOUND,
                message = ""
            )
        )
    resume.result = body_validated.result
    resume.status = AnalysisStatus.SUCCESS
    session.add(resume)
    session.commit()
    response.status_code = 200
    return {}

@internal_router.post("/cover_letter/success")
async def success_cover_letter(body: Annotated[dict, Depends(check_internal)], session: SessionDep, response: Response):
    body_validated = success_model_validate(body)
    statement = select(CoverLetter).where(CoverLetter.id == body_validated.analysis_id)
    resume = session.exec(statement).one_or_none()
    if resume is None:
        raise AppException(
            status_code = 404,
            error = ErrorResponse(
                code = ErrorResponseCode.NOT_FOUND,
                message = ""
            )
        )
    resume.result = body_validated.result
    resume.status = AnalysisStatus.SUCCESS
    session.add(resume)
    session.commit()
    response.status_code = 200
    return {}