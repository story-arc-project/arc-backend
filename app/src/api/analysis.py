import traceback
import requests
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, Response
from sqlmodel import col, select

from src.api.models.base import ComprehensiveAnalysisList, ComprehensiveAnalysisListData, ErrorResponse, IndividualAnalysisData, IndividualAnalysisList, IndividualAnalysisListData, SuccessResponse
from src.api.models.exc import AppException
from src.api.models.request import ComprehensiveAnalysisPostRequest
from src.api.models.response import ComprehensiveAnalysisListResponse, IndividualAnalysisListResponse, IndividualAnalysisResponse
from src.db.db import SessionDep
from src.db.models import ComprehensiveAnalysis, Experience, IndividualAnalysis
from src.enums import ErrorResponseCode
from src.utils.auth import check_auth
from src.utils.token import AccessTokenPayload

analysis_router = APIRouter()

@analysis_router.get("/individual")
async def get_individual_analyses(session: SessionDep, response: Response, payload: Annotated[AccessTokenPayload, Depends(check_auth)]):
    statement = (
        select(IndividualAnalysis)
        .join(Experience)
        .where(Experience.user_id == payload.sub)
    )
    result = session.exec(statement).all()
    response.status_code = 200
    return IndividualAnalysisListResponse(
        message = "Fetch success.",
        data = IndividualAnalysisList(
            count = len(result),
            contents = [IndividualAnalysisListData(
                id = analysis.id,
                status = analysis.status,
                experience_id = analysis.experience_id
            ) for analysis in result]
        )
    )

@analysis_router.get("/individual/{analysis_id}")
async def get_individual_analysis(analysis_id: UUID, session: SessionDep, response: Response, payload: Annotated[AccessTokenPayload, Depends(check_auth)]):
    statement = (
        select(IndividualAnalysis, Experience)
        .join(Experience)
        .where(IndividualAnalysis.id == analysis_id)
    )
    result = session.exec(statement).one_or_none()
    if result is None:
        raise AppException(
            404,
            ErrorResponse(
                code = ErrorResponseCode.NOT_FOUND,
                message = "Analysis not found"
            )
        )
    analysis, experience = result
    if experience.user_id != payload.sub:
        raise AppException(
            403,
            ErrorResponse(
                code = ErrorResponseCode.RESOURCE_NOT_ALLOWED,
                message = "Access for the resource is not allowed"
            )
        )
    response.status_code = 200
    return IndividualAnalysisResponse(
        message = "Fetch success.",
        data = IndividualAnalysisData(**analysis.model_dump())
    )

@analysis_router.post("/comprehensive")
async def post_comprehensive_analysis(body: ComprehensiveAnalysisPostRequest, session: SessionDep, response: Response, payload: Annotated[AccessTokenPayload, Depends(check_auth)]):
    statement = select(Experience).where(col(Experience.id).in_(body.experiences))
    result = session.exec(statement).all()
    user_input: list[str] = []
    for experience in result:
        user_input.append(str(experience.content))
    try:
        new_comprehensive_analysis = ComprehensiveAnalysis(
            experiences = [experience for experience in result]
        )
        for experience in result:
            if experience.user_id != payload.sub:
                raise AppException(
                    403,
                    ErrorResponse(
                        code = ErrorResponseCode.RESOURCE_NOT_ALLOWED,
                        message = "Access for the resource is not allowed"
                    )
                )
        req = requests.post("http://ai_analyst:8001/comprehensive", json={
            "analysis_id": new_comprehensive_analysis.id,
            "input": user_input
        })
        req.raise_for_status()
        new_comprehensive_analysis.task_id = req.json()["task_id"]
        session.add(new_comprehensive_analysis)
        session.commit()
        session.refresh(new_comprehensive_analysis)
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
    return SuccessResponse(
        message = "Queued new comprehensive analysis."
    )

@analysis_router.get("/comprehensive")
async def get_comprehensive_analyses(session: SessionDep, response: Response, payload: Annotated[AccessTokenPayload, Depends(check_auth)]):
    statement = (
        select(ComprehensiveAnalysis)
        .where(ComprehensiveAnalysis.experiences[0].user_id == payload.sub)
    )
    result = session.exec(statement).all()
    response.status_code = 200
    return ComprehensiveAnalysisListResponse(
        message = "Fetch success.",
        data = ComprehensiveAnalysisList(
            count = len(result),
            contents = [ComprehensiveAnalysisListData(
                id = analysis.id,
                status = analysis.status,
                experience_ids = [experience.id for experience in analysis.experiences]
            ) for analysis in result]
        )
    )