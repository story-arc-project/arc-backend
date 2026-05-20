import traceback
import requests
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, Response
from sqlmodel import col, select
import json

from src.api.models.base import ComprehensiveAnalysisData, ComprehensiveAnalysisList, ComprehensiveAnalysisListData, ErrorResponse, IndividualAnalysisData, IndividualAnalysisList, IndividualAnalysisListData, SuccessResponse, KeywordAnalysisList, KeywordAnalysisListData, KeywordAnalysisData
from src.api.models.exc import AppException
from src.api.models.request import ComprehensiveAnalysisPostRequest, KeywordAnalysisPostRequest
from src.api.models.response import ComprehensiveAnalysisListResponse, ComprehensiveAnalysisResponse, DeleteSuccessResponse, IndividualAnalysisListResponse, IndividualAnalysisResponse, KeywordAnalysisListResponse, KeywordAnalysisResponse
from src.db.db import SessionDep
from src.db.models import ComprehensiveAnalysis, Experience, IndividualAnalysis, KeywordAnalysis, UserProfile
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
    user_profile = session.exec(select(UserProfile).where(UserProfile.user_id == payload.sub)).one_or_none()
    if user_profile is None:
        raise AppException(
            404,
            ErrorResponse(
                code = ErrorResponseCode.NOT_FOUND,
                message = "User profile not found"
            )
        )
    user_input: list[str] = []
    for experience in result:
        user_input.append(str(experience.content))
    try:
        new_comprehensive_analysis = ComprehensiveAnalysis(
            user_id = payload.sub,
            experience_ids = [experience.id for experience in result]
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
            "analysis_id": str(new_comprehensive_analysis.id),
            "input": user_input,
            "school": user_profile.school,
            "department": user_profile.department
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
        .where(ComprehensiveAnalysis.user_id == payload.sub)
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
                experience_ids = analysis.experience_ids
            ) for analysis in result]
        )
    )

@analysis_router.get("/comprehensive/{analysis_id}")
async def get_comprehensive_analysis(analysis_id: UUID, session: SessionDep, response: Response, payload: Annotated[AccessTokenPayload, Depends(check_auth)]):
    statement = (
        select(ComprehensiveAnalysis)
        .where(ComprehensiveAnalysis.id == analysis_id)
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
    if result.user_id != payload.sub:
        raise AppException(
            403,
            ErrorResponse(
                code = ErrorResponseCode.RESOURCE_NOT_ALLOWED,
                message = "Access for the resource is not allowed"
            )
        )
    response.status_code = 200
    return ComprehensiveAnalysisResponse(
        message = "Fetch success.",
        data = ComprehensiveAnalysisData(
            id = result.id,
            status = result.status,
            experience_ids = result.experience_ids,
            result = result.result
        )
    )

@analysis_router.delete("/comprehensive/{analysis_id}")
async def delete_comprehensive_analysis(analysis_id: UUID, session: SessionDep, response: Response, payload: Annotated[AccessTokenPayload, Depends(check_auth)]):
    statement = (
        select(ComprehensiveAnalysis)
        .where(ComprehensiveAnalysis.id == analysis_id)
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
        message = "Comprehensive analysis deleted."
    )

@analysis_router.post("/keyword")
async def post_keyword_analysis(body: KeywordAnalysisPostRequest, session: SessionDep, response: Response, payload: Annotated[AccessTokenPayload, Depends(check_auth)]):
    statement = select(Experience).where(Experience.user_id == payload.sub)
    result = session.exec(statement).all()
    user_input: list[str] = []
    for experience in result:
        user_input.append(str(experience.content))
    try:
        new_keyword_analysis = KeywordAnalysis(
            user_id = payload.sub,
            keywords = body.keywords
        )
        req = requests.post("http://ai_analyst:8001/keyword", json={
            "analysis_id": str(new_keyword_analysis.id),
            "input": json.dumps(user_input),
            "keywords": body.keywords
        })
        req.raise_for_status()
        new_keyword_analysis.task_id = req.json()["task_id"]
        session.add(new_keyword_analysis)
        session.commit()
        session.refresh(new_keyword_analysis)
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
        message = "Queued new keyword analysis."
    )

@analysis_router.get("/keyword")
async def get_keyword_analyses(session: SessionDep, response: Response, payload: Annotated[AccessTokenPayload, Depends(check_auth)]):
    statement = (
        select(KeywordAnalysis).where(KeywordAnalysis.user_id == payload.sub)
    )
    result = session.exec(statement).all()
    response.status_code = 200
    return KeywordAnalysisListResponse(
        message = "Fetch success.",
        data = KeywordAnalysisList(
            count = len(result),
            contents = [KeywordAnalysisListData(
                id = analysis.id,
                status = analysis.status,
                keywords = analysis.keywords
            ) for analysis in result]
        )
    )

@analysis_router.get("/keyword/{analysis_id}")
async def get_keyword_analysis(analysis_id: UUID, session: SessionDep, response: Response, payload: Annotated[AccessTokenPayload, Depends(check_auth)]):
    statement = (
        select(KeywordAnalysis)
        .where(KeywordAnalysis.id == analysis_id)
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
    if result.user_id != payload.sub:
        raise AppException(
            403,
            ErrorResponse(
                code = ErrorResponseCode.RESOURCE_NOT_ALLOWED,
                message = "Access for the resource is not allowed"
            )
        )
    response.status_code = 200
    return KeywordAnalysisResponse(
        message = "Fetch success.",
        data = KeywordAnalysisData(
            id = result.id,
            status = result.status,
            keywords = result.keywords,
            result = result.result
        )
    )

@analysis_router.delete("/keyword/{analysis_id}")
async def delete_keyword_analysis(analysis_id: UUID, session: SessionDep, response: Response, payload: Annotated[AccessTokenPayload, Depends(check_auth)]):
    statement = (
        select(KeywordAnalysis)
        .where(KeywordAnalysis.id == analysis_id)
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
        message = "Keyword analysis deleted."
    )