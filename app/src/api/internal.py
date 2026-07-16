import json
from sqlmodel import select
from typing import Annotated, Any
from uuid import UUID
from fastapi import APIRouter, Depends, Response

from src.api.models.base import ErrorResponse
from src.api.models.exc import AppException
from src.db.db import SessionDep
from src.db.models import ComprehensiveAnalysis, IndividualAnalysis, KeywordAnalysis, Resume
from src.enums import AnalysisStatus, ErrorResponseCode
from src.utils.internal import check_internal

internal_router = APIRouter()

@internal_router.post("/{analysis_type}/failure")
async def fail_individual(analysis_type: str, body: Annotated[dict[str, Any], Depends(check_internal)], session: SessionDep, response: Response):
    analysis_id: str | None = body.get("analysis_id")
    if analysis_id is None:
        raise AppException(
            status_code = 400,
            error = ErrorResponse(
                code = ErrorResponseCode.BAD_REQUEST,
                message = ""
            )
        )
    if analysis_type == "individual":
        statement = select(IndividualAnalysis).where(IndividualAnalysis.id == UUID(analysis_id))
    elif analysis_type == "comprehensive":
        statement = select(ComprehensiveAnalysis).where(ComprehensiveAnalysis.id == UUID(analysis_id))
    elif analysis_type == "keyword":
        statement = select(KeywordAnalysis).where(KeywordAnalysis.id == UUID(analysis_id))
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

@internal_router.post("/individual/success")
async def success_individual(body: Annotated[dict[str, Any], Depends(check_internal)], session: SessionDep, response: Response):
    analysis_id: str | None = body.get("analysis_id")
    result: dict | None = body.get("result")
    if analysis_id is None or result is None:
        raise AppException(
            status_code = 400,
            error = ErrorResponse(
                code = ErrorResponseCode.BAD_REQUEST,
                message = ""
            )
        )
    statement = select(IndividualAnalysis).where(IndividualAnalysis.id == UUID(analysis_id))
    analysis = session.exec(statement).one_or_none()
    if analysis is None:
        raise AppException(
            status_code = 404,
            error = ErrorResponse(
                code = ErrorResponseCode.NOT_FOUND,
                message = ""
            )
        )
    analysis_result: dict[str, Any] = result
    analysis.vector = analysis_result.get("vector")
    analysis.result = analysis_result.get("result")
    analysis.status = AnalysisStatus.SUCCESS
    session.add(analysis)
    session.commit()
    response.status_code = 200
    return {}

@internal_router.post("/comprehensive/success")
async def success_comprehensive(body: Annotated[dict[str, Any], Depends(check_internal)], session: SessionDep, response: Response):
    analysis_id: str | None = body.get("analysis_id")
    result: dict | None = body.get("result")
    if analysis_id is None or result is None:
        raise AppException(
            status_code = 400,
            error = ErrorResponse(
                code = ErrorResponseCode.BAD_REQUEST,
                message = ""
            )
        )
    statement = select(ComprehensiveAnalysis).where(ComprehensiveAnalysis.id == UUID(analysis_id))
    analysis = session.exec(statement).one_or_none()
    if analysis is None:
        raise AppException(
            status_code = 404,
            error = ErrorResponse(
                code = ErrorResponseCode.NOT_FOUND,
                message = ""
            )
        )
    analysis_result: dict[str, Any] = result
    analysis.vector = analysis_result.get("vector")
    analysis.result = analysis_result.get("result")
    analysis.status = AnalysisStatus.SUCCESS
    session.add(analysis)
    session.commit()
    response.status_code = 200
    return {}

@internal_router.post("/keyword/success")
async def success_keyword(body: Annotated[dict[str, Any], Depends(check_internal)], session: SessionDep, response: Response):
    analysis_id: str | None = body.get("analysis_id")
    result: dict | None = body.get("result")
    if analysis_id is None or result is None:
        raise AppException(
            status_code = 400,
            error = ErrorResponse(
                code = ErrorResponseCode.BAD_REQUEST,
                message = ""
            )
        )
    statement = select(KeywordAnalysis).where(KeywordAnalysis.id == UUID(analysis_id))
    analysis = session.exec(statement).one_or_none()
    if analysis is None:
        raise AppException(
            status_code = 404,
            error = ErrorResponse(
                code = ErrorResponseCode.NOT_FOUND,
                message = ""
            )
        )
    analysis.result = result
    analysis.status = AnalysisStatus.SUCCESS
    session.add(analysis)
    session.commit()
    response.status_code = 200
    return {}

@internal_router.post("/resume/success")
async def success_resume(body: Annotated[dict[str, Any], Depends(check_internal)], session: SessionDep, response: Response):
    resume_id: str | None = body.get("resume_id")
    result: dict | None = body.get("result")
    if resume_id is None or result is None:
        raise AppException(
            status_code = 400,
            error = ErrorResponse(
                code = ErrorResponseCode.BAD_REQUEST,
                message = ""
            )
        )
    statement = select(Resume).where(Resume.id == UUID(resume_id))
    resume = session.exec(statement).one_or_none()
    if resume is None:
        raise AppException(
            status_code = 404,
            error = ErrorResponse(
                code = ErrorResponseCode.NOT_FOUND,
                message = ""
            )
        )
    resume.result = result
    session.add(resume)
    session.commit()
    response.status_code = 200
    return {}