from datetime import datetime
import traceback
from zoneinfo import ZoneInfo
import requests
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, Response
from sqlmodel import col, select, and_
import json

from src.api.models.base import BookmarkData, ComprehensiveAnalysisData, ComprehensiveAnalysisExperienceData, ComprehensiveAnalysisList, ComprehensiveAnalysisListData, ErrorResponse, IndividualAnalysisData, IndividualAnalysisList, IndividualAnalysisListData, SuccessResponse, KeywordAnalysisList, KeywordAnalysisListData, KeywordAnalysisData, UUIDDataWithTitle
from src.api.models.exc import AppException
from src.api.models.request import ComprehensiveAnalysisPatchRequest, ComprehensiveAnalysisPostRequest, KeywordAnalysisPatchRequest, KeywordAnalysisPostRequest
from src.api.models.response import BookmarkListResponse, ComprehensiveAnalysisListResponse, ComprehensiveAnalysisResponse, DeleteSuccessResponse, IndividualAnalysisListResponse, IndividualAnalysisResponse, KeywordAnalysisListResponse, KeywordAnalysisResponse, PostSuccessResponse
from src.db.db import SessionDep
from src.db.models import AnalysisBookmark, ComprehensiveAnalysis, Experience, IndividualAnalysis, KeywordAnalysis, UserProfile
from src.enums import AnalysisStatus, AnalysisType, ErrorResponseCode
from src.utils.auth import check_auth
from src.utils.ratelimit import analysis_rate_limiters
from src.utils.render import render_experience_content
from src.utils.token import AccessTokenPayload

def get_experience_titles(session: SessionDep, experience_ids: set[UUID]):
    experience_titles: dict[UUID, str] = {}
    if len(experience_ids) == 0:
        return experience_titles
    experience_rows = session.exec(
        select(Experience.id, Experience.content)
        .where(col(Experience.id).in_(experience_ids))
    ).all()
    for experience_row in experience_rows:
        exp_id, content = experience_row
        experience_titles[exp_id] = content.get("title", "")
    if len(experience_titles) != len(experience_ids):
        print("Warning: Experience titles and ids length do not match")
        print(experience_ids)
        print(experience_titles)
    return experience_titles

analysis_router = APIRouter()

@analysis_router.get("/individual")
async def get_individual_analyses(session: SessionDep, response: Response, payload: Annotated[AccessTokenPayload, Depends(check_auth)]):
    statement = (
        select(IndividualAnalysis, Experience, AnalysisBookmark)
        .join(Experience)
        .outerjoin(
            AnalysisBookmark,
            and_(
                AnalysisBookmark.analysis_id == IndividualAnalysis.id,
                AnalysisBookmark.analysis_type == AnalysisType.individual,
                AnalysisBookmark.user_id == payload.sub
            )
        )
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
                experience_id = analysis.experience_id,
                title = experience.content.get("title", ""),
                created_at = analysis.created_at,
                updated_at = analysis.updated_at,
                is_bookmarked = (bookmark is not None)
            ) for analysis, experience, bookmark in result]
        )
    )

@analysis_router.get("/individual/{analysis_id}")
async def get_individual_analysis(analysis_id: UUID, session: SessionDep, response: Response, payload: Annotated[AccessTokenPayload, Depends(check_auth)]):
    statement = (
        select(IndividualAnalysis, Experience, AnalysisBookmark)
        .join(Experience)
        .outerjoin(
            AnalysisBookmark,
            and_(
                AnalysisBookmark.analysis_id == IndividualAnalysis.id,
                AnalysisBookmark.analysis_type == AnalysisType.individual,
                AnalysisBookmark.user_id == payload.sub
            )
        )
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
    analysis, experience, bookmark = result
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
        data = IndividualAnalysisData(
            id = analysis.id,
            status = analysis.status,
            experience_id = analysis.experience_id,
            title = experience.content.get("title", ""),
            created_at = analysis.created_at,
            updated_at = analysis.updated_at,
            result = analysis.result,
            is_bookmarked = (bookmark is not None)
        )
    )

def fetch_owned_experiences(session: SessionDep, experience_ids: list[UUID], user_id: UUID):
    statement = select(Experience).where(col(Experience.id).in_(experience_ids))
    result = session.exec(statement).all()
    if len(result) == 0:
        raise AppException(
            status_code = 400,
            error = ErrorResponse(
                code = ErrorResponseCode.BAD_REQUEST,
                message = "No available experiences"
            )
        )
    for experience in result:
        if experience.user_id != user_id:
            raise AppException(
                403,
                ErrorResponse(
                    code = ErrorResponseCode.RESOURCE_NOT_ALLOWED,
                    message = "Access for the resource is not allowed"
                )
            )
    return result

def pre_process_comprehensive_analysis(session: SessionDep, experience_ids: list[UUID], user_id: UUID):
    user_profile = session.exec(select(UserProfile).where(UserProfile.user_id == user_id)).one_or_none()
    if user_profile is None:
        raise AppException(
            404,
            ErrorResponse(
                code = ErrorResponseCode.NOT_FOUND,
                message = "User profile not found"
            )
        )
    experiences = fetch_owned_experiences(session, experience_ids, user_id)
    user_input = [render_experience_content(experience.content) for experience in experiences]
    experience_ids = [experience.id for experience in experiences]
    return user_profile, user_input, experience_ids

def generate_comprehensive_analysis_title(session: SessionDep, experience_ids: list[UUID]):
    titles = get_experience_titles(session, set(experience_ids))
    valid_titles = [title for title in titles.values() if len(title) != 0]
    if len(valid_titles) == 0:
        title = f"{datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d")} 종합 분석"
    elif len(experience_ids) == 1:
        title = f"{valid_titles[0]} 분석"
    else:
        title = f"{valid_titles[0]} 등 {len(experience_ids)}개 분석"
    return title

def process_comprehensive_analysis(analysis: ComprehensiveAnalysis, user_input: list[str], user_profile: UserProfile, session: SessionDep, response: Response):
    try:
        req = requests.post("http://ai_analyst:8001/comprehensive", json={
            "analysis_id": str(analysis.id),
            "input": user_input,
            "school": user_profile.school,
            "department": user_profile.department
        })
        req.raise_for_status()
        analysis.task_id = req.json()["task_id"]
        analysis.status = AnalysisStatus.QUEUED
        session.add(analysis)
        session.commit()
        session.refresh(analysis)
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
        message = "Queued comprehensive analysis.",
        data = UUIDDataWithTitle(
            id = analysis.id,
            title = analysis.title
        )
    )

@analysis_router.post("/comprehensive")
async def post_comprehensive_analysis(
    body: ComprehensiveAnalysisPostRequest,
    session: SessionDep,
    response: Response,
    payload: Annotated[AccessTokenPayload, Depends(check_auth)],
    _user_limit: Annotated[None, Depends(analysis_rate_limiters["comprehensive"]["user"])],
    _ip_limit: Annotated[None, Depends(analysis_rate_limiters["comprehensive"]["ip"])]
):
    user_profile, user_input, experience_ids = pre_process_comprehensive_analysis(session, body.experiences, payload.sub)
    title = generate_comprehensive_analysis_title(session, experience_ids)
    new_comprehensive_analysis = ComprehensiveAnalysis(
        user_id = payload.sub,
        experience_ids = experience_ids,
        title = title
    )
    return process_comprehensive_analysis(new_comprehensive_analysis, user_input, user_profile, session, response)

@analysis_router.post("/comprehensive/{analysis_id}/retry")
async def retry_comprehensive_analysis(
    analysis_id: UUID,
    session: SessionDep,
    response: Response,
    payload: Annotated[AccessTokenPayload, Depends(check_auth)],
    _user_limit: Annotated[None, Depends(analysis_rate_limiters["comprehensive"]["user"])],
    _ip_limit: Annotated[None, Depends(analysis_rate_limiters["comprehensive"]["ip"])]
):
    analysis = session.get(ComprehensiveAnalysis, analysis_id)
    if analysis is None:
        raise AppException(
            404,
            ErrorResponse(
                code = ErrorResponseCode.NOT_FOUND,
                message = "Comprehensive analysis not found"
            )
        )
    if analysis.user_id != payload.sub:
        raise AppException(
            403,
            ErrorResponse(
                code = ErrorResponseCode.RESOURCE_NOT_ALLOWED,
                message = "Access for the resource is not allowed"
            )
        )
    if analysis.status != AnalysisStatus.FAILED:
        raise AppException(
            400,
            ErrorResponse(
                code = ErrorResponseCode.BAD_REQUEST,
                message = "Analysis is not in failed status"
            )
        )
    user_profile, user_input, _ = pre_process_comprehensive_analysis(session, analysis.experience_ids, payload.sub)
    return process_comprehensive_analysis(analysis, user_input, user_profile, session, response)

@analysis_router.patch("/comprehensive/{analysis_id}")
async def patch_comprehensive_analysis(
    analysis_id: UUID,
    body: ComprehensiveAnalysisPatchRequest,
    session: SessionDep,
    response: Response,
    payload: Annotated[AccessTokenPayload, Depends(check_auth)]
):
    analysis = session.get(ComprehensiveAnalysis, analysis_id)
    if analysis is None:
        raise AppException(
            404,
            ErrorResponse(
                code = ErrorResponseCode.NOT_FOUND,
                message = "Comprehensive analysis not found"
            )
        ) 
    if analysis.user_id != payload.sub:
        raise AppException(
            403,
            ErrorResponse(
                code = ErrorResponseCode.RESOURCE_NOT_ALLOWED,
                message = "Access for the resource is not allowed"
            )
        )
    analysis.title = body.title
    try:
        session.add(analysis)
        session.commit()
        session.refresh(analysis)
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
        message = "Comprehensive analysis patch success.",
        data = UUIDDataWithTitle(
            id = analysis.id,
            title = body.title
        )
    )
    
@analysis_router.get("/comprehensive")
async def get_comprehensive_analyses(session: SessionDep, response: Response, payload: Annotated[AccessTokenPayload, Depends(check_auth)]):
    statement = (
        select(ComprehensiveAnalysis, AnalysisBookmark)
        .outerjoin(
            AnalysisBookmark,
            and_(
                AnalysisBookmark.analysis_id == ComprehensiveAnalysis.id,
                AnalysisBookmark.analysis_type == AnalysisType.comprehensive,
                AnalysisBookmark.user_id == payload.sub
            )
        )
        .where(ComprehensiveAnalysis.user_id == payload.sub)
    )
    result = session.exec(statement).all()
    experience_ids = {
        exp_id
        for analysis, _ in result
        for exp_id in analysis.experience_ids
    }
    experience_titles = get_experience_titles(session, experience_ids)
    response.status_code = 200
    return ComprehensiveAnalysisListResponse(
        message = "Fetch success.",
        data = ComprehensiveAnalysisList(
            count = len(result),
            contents = [ComprehensiveAnalysisListData(
                id = analysis.id,
                status = analysis.status,
                experiences = [
                    ComprehensiveAnalysisExperienceData(
                        id = exp_id,
                        title = experience_titles.get(exp_id)
                    )
                    for exp_id in analysis.experience_ids
                ],
                created_at = analysis.created_at,
                updated_at = analysis.updated_at,
                is_bookmarked = (bookmark is not None),
                title = analysis.title
            ) for analysis, bookmark in result]
        )
    )

@analysis_router.get("/comprehensive/{analysis_id}")
async def get_comprehensive_analysis(analysis_id: UUID, session: SessionDep, response: Response, payload: Annotated[AccessTokenPayload, Depends(check_auth)]):
    statement = (
        select(ComprehensiveAnalysis, AnalysisBookmark)
        .outerjoin(
            AnalysisBookmark,
            and_(
                AnalysisBookmark.analysis_id == ComprehensiveAnalysis.id,
                AnalysisBookmark.analysis_type == AnalysisType.comprehensive,
                AnalysisBookmark.user_id == payload.sub
            )
        )
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
    analysis, bookmark = result
    if analysis.user_id != payload.sub:
        raise AppException(
            403,
            ErrorResponse(
                code = ErrorResponseCode.RESOURCE_NOT_ALLOWED,
                message = "Access for the resource is not allowed"
            )
        )
    experience_ids = {
        exp_id
        for exp_id in analysis.experience_ids
    }
    experience_titles = get_experience_titles(session, experience_ids)
    response.status_code = 200
    return ComprehensiveAnalysisResponse(
        message = "Fetch success.",
        data = ComprehensiveAnalysisData(
            id = analysis.id,
            status = analysis.status,
            experiences = [
                ComprehensiveAnalysisExperienceData(
                    id = exp_id,
                    title = experience_titles.get(exp_id)
                )
                for exp_id in analysis.experience_ids
            ],
            result = analysis.result,
            created_at = analysis.created_at,
            updated_at = analysis.updated_at,
            is_bookmarked = (bookmark is not None),
            title = analysis.title
        )
    )

@analysis_router.delete("/comprehensive/{analysis_id}")
async def delete_comprehensive_analysis(analysis_id: UUID, session: SessionDep, response: Response, payload: Annotated[AccessTokenPayload, Depends(check_auth)]):
    statement = (
        select(ComprehensiveAnalysis, AnalysisBookmark)
        .outerjoin(
            AnalysisBookmark,
            and_(
                AnalysisBookmark.analysis_id == ComprehensiveAnalysis.id,
                AnalysisBookmark.analysis_type == AnalysisType.comprehensive,
                AnalysisBookmark.user_id == payload.sub
            )
        )
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
    analysis, bookmark = result
    if analysis.user_id != payload.sub:
        raise AppException(
            403,
            ErrorResponse(
                code = ErrorResponseCode.RESOURCE_NOT_ALLOWED,
                message = "Access for the resource is not allowed"
            )
        )
    try:
        session.delete(analysis)
        if bookmark is not None:
            session.delete(bookmark)
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
        message = "Comprehensive analysis deleted."
    )

def pre_process_keyword_analysis(session: SessionDep, user_id: UUID):
    statement = select(Experience).where(Experience.user_id == user_id)
    result = session.exec(statement).all()
    user_input = [render_experience_content(experience.content) for experience in result]
    return user_input

def generate_keyword_analysis_title(keywords: list[str]):
    if len(keywords) > 3:
        title = f"{", ".join(keywords[:3])} 외 {len(keywords) - 3}개 분석"
    else:
        title = f"{", ".join(keywords)} 분석"
    return title

def process_keyword_analysis(analysis: KeywordAnalysis, user_input: list[str], session: SessionDep, response: Response):
    try:
        req = requests.post("http://ai_analyst:8001/keyword", json={
            "analysis_id": str(analysis.id),
            "input": json.dumps(user_input),
            "keywords": analysis.keywords,
            "target": analysis.target
        })
        req.raise_for_status()
        analysis.task_id = req.json()["task_id"]
        analysis.status = AnalysisStatus.QUEUED
        session.add(analysis)
        session.commit()
        session.refresh(analysis)
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
        message = "Queued keyword analysis.",
        data = UUIDDataWithTitle(
            id = analysis.id,
            title = analysis.title
        )
    )

@analysis_router.post("/keyword")
async def post_keyword_analysis(
    body: KeywordAnalysisPostRequest,
    session: SessionDep,
    response: Response,
    payload: Annotated[AccessTokenPayload, Depends(check_auth)],
    _user_limit: Annotated[None, Depends(analysis_rate_limiters["keyword"]["user"])],
    _ip_limit: Annotated[None, Depends(analysis_rate_limiters["keyword"]["ip"])]
):
    user_input = pre_process_keyword_analysis(session, payload.sub)
    title = generate_keyword_analysis_title(body.keywords)
    new_keyword_analysis = KeywordAnalysis(
        user_id = payload.sub,
        keywords = body.keywords,
        title = title,
        target = body.target
    )
    return process_keyword_analysis(new_keyword_analysis, user_input, session, response)

@analysis_router.post("/keyword/{analysis_id}/retry")
async def retry_keyword_analysis(
    analysis_id: UUID,
    session: SessionDep,
    response: Response,
    payload: Annotated[AccessTokenPayload, Depends(check_auth)],
    _user_limit: Annotated[None, Depends(analysis_rate_limiters["keyword"]["user"])],
    _ip_limit: Annotated[None, Depends(analysis_rate_limiters["keyword"]["ip"])]
):
    analysis = session.get(KeywordAnalysis, analysis_id)
    if analysis is None:
        raise AppException(
            404,
            ErrorResponse(
                code = ErrorResponseCode.NOT_FOUND,
                message = "Keyword analysis not found"
            )
        )
    if analysis.user_id != payload.sub:
        raise AppException(
            403,
            ErrorResponse(
                code = ErrorResponseCode.RESOURCE_NOT_ALLOWED,
                message = "Access for the resource is not allowed"
            )
        )
    if analysis.status != AnalysisStatus.FAILED:
        raise AppException(
            400,
            ErrorResponse(
                code = ErrorResponseCode.BAD_REQUEST,
                message = "Analysis is not in failed status"
            )
        )
    user_input = pre_process_keyword_analysis(session, payload.sub)
    return process_keyword_analysis(analysis, user_input, session, response)

@analysis_router.patch("/keyword/{analysis_id}")
async def patch_keyword_analysis(
    analysis_id: UUID,
    body: KeywordAnalysisPatchRequest,
    session: SessionDep,
    response: Response,
    payload: Annotated[AccessTokenPayload, Depends(check_auth)]
):
    analysis = session.get(KeywordAnalysis, analysis_id)
    if analysis is None:
        raise AppException(
            404,
            ErrorResponse(
                code = ErrorResponseCode.NOT_FOUND,
                message = "Keyword analysis not found"
            )
        ) 
    if analysis.user_id != payload.sub:
        raise AppException(
            403,
            ErrorResponse(
                code = ErrorResponseCode.RESOURCE_NOT_ALLOWED,
                message = "Access for the resource is not allowed"
            )
        )
    analysis.title = body.title
    try:
        session.add(analysis)
        session.commit()
        session.refresh(analysis)
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
            id = analysis.id,
            title = body.title
        )
    )

@analysis_router.get("/keyword")
async def get_keyword_analyses(session: SessionDep, response: Response, payload: Annotated[AccessTokenPayload, Depends(check_auth)]):
    statement = (
        select(KeywordAnalysis, AnalysisBookmark)
        .outerjoin(
            AnalysisBookmark,
            and_(
                AnalysisBookmark.analysis_id == KeywordAnalysis.id,
                AnalysisBookmark.analysis_type == AnalysisType.keyword,
                AnalysisBookmark.user_id == payload.sub
            )
        )
        .where(KeywordAnalysis.user_id == payload.sub)
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
                keywords = analysis.keywords,
                target = analysis.target,
                created_at = analysis.created_at,
                updated_at = analysis.updated_at,
                is_bookmarked = (bookmark is not None),
                title = analysis.title
            ) for analysis, bookmark in result]
        )
    )

@analysis_router.get("/keyword/{analysis_id}")
async def get_keyword_analysis(analysis_id: UUID, session: SessionDep, response: Response, payload: Annotated[AccessTokenPayload, Depends(check_auth)]):
    statement = (
        select(KeywordAnalysis, AnalysisBookmark)
        .outerjoin(
            AnalysisBookmark,
            and_(
                AnalysisBookmark.analysis_id == KeywordAnalysis.id,
                AnalysisBookmark.analysis_type == AnalysisType.keyword,
                AnalysisBookmark.user_id == payload.sub
            )
        )
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
    analysis, bookmark = result
    if analysis.user_id != payload.sub:
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
            id = analysis.id,
            status = analysis.status,
            keywords = analysis.keywords,
            target = analysis.target,
            result = analysis.result,
            created_at = analysis.created_at,
            updated_at = analysis.updated_at,
            is_bookmarked = (bookmark is not None),
            title = analysis.title
        )
    )

@analysis_router.delete("/keyword/{analysis_id}")
async def delete_keyword_analysis(analysis_id: UUID, session: SessionDep, response: Response, payload: Annotated[AccessTokenPayload, Depends(check_auth)]):
    statement = (
        select(KeywordAnalysis, AnalysisBookmark)
        .outerjoin(
            AnalysisBookmark,
            and_(
                AnalysisBookmark.analysis_id == KeywordAnalysis.id,
                AnalysisBookmark.analysis_type == AnalysisType.keyword,
                AnalysisBookmark.user_id == payload.sub
            )
        )
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
    analysis, bookmark = result
    if analysis.user_id != payload.sub:
        raise AppException(
            403,
            ErrorResponse(
                code = ErrorResponseCode.RESOURCE_NOT_ALLOWED,
                message = "Access for the resource is not allowed"
            )
        )
    try:
        session.delete(analysis)
        if bookmark is not None:
            session.delete(bookmark)
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
        message = "Keyword analysis deleted."
    )

@analysis_router.get("/bookmarks")
async def get_bookmarks(session: SessionDep, response: Response, payload: Annotated[AccessTokenPayload, Depends(check_auth)]):
    statement = (
        select(AnalysisBookmark)
        .where(AnalysisBookmark.user_id == payload.sub)
    )
    result = session.exec(statement).all()
    response.status_code = 200
    data: list[BookmarkData] = []
    for bookmark in result:
        if bookmark.analysis_type == AnalysisType.comprehensive:
            analysis = session.get(ComprehensiveAnalysis, bookmark.analysis_id)
            if analysis is None:
                continue
            data.append(BookmarkData(
                id = analysis.id,
                type = AnalysisType.comprehensive,
                title = analysis.title,
                status = analysis.status,
                created_at = bookmark.created_at,
                updated_at = bookmark.updated_at
            ))
        elif bookmark.analysis_type == AnalysisType.keyword:
            analysis = session.get(KeywordAnalysis, bookmark.analysis_id)
            if analysis is None:
                continue
            data.append(BookmarkData(
                id = analysis.id,
                type = AnalysisType.keyword,
                title = analysis.title,
                status = analysis.status,
                created_at = bookmark.created_at,
                updated_at = bookmark.updated_at
            ))
        elif bookmark.analysis_type == AnalysisType.individual:
            analysis = session.get(IndividualAnalysis, bookmark.analysis_id)
            if analysis is None:
                continue
            experience = session.get(Experience, analysis.experience_id)
            if experience is None:
                continue
            data.append(BookmarkData(
                id = analysis.id,
                type = AnalysisType.individual,
                title = experience.content.get("title", ""),
                status = analysis.status,
                created_at = bookmark.created_at,
                updated_at = bookmark.updated_at
            ))
    return BookmarkListResponse(
        message = "Fetch success.",
        data = data
    )

@analysis_router.post("/bookmarks/{analysis_id}")
async def add_bookmark(analysis_id: UUID, session: SessionDep, response: Response, payload: Annotated[AccessTokenPayload, Depends(check_auth)]):
    analysis_type = None
    owner_id = None
    for model, type_name in (
        (IndividualAnalysis, AnalysisType.individual),
        (ComprehensiveAnalysis, AnalysisType.comprehensive),
        (KeywordAnalysis, AnalysisType.keyword),
    ):
        statement = select(model).where(model.id == analysis_id)
        result = session.exec(statement).one_or_none()
        if result is not None:
            analysis_type = type_name
            owner_id = result.user_id
            break
    if analysis_type is None:
        raise AppException(
            404,
            ErrorResponse(
                code=ErrorResponseCode.NOT_FOUND,
                message="Analysis not found"
            )
        )
    if owner_id != payload.sub:
        raise AppException(
            403,
            ErrorResponse(
                code=ErrorResponseCode.RESOURCE_NOT_ALLOWED,
                message="Access for the resource is not allowed"
            )
        )
    existing_statement = (
        select(AnalysisBookmark)
        .where(AnalysisBookmark.user_id == payload.sub)
        .where(AnalysisBookmark.analysis_id == analysis_id)
        .where(AnalysisBookmark.analysis_type == analysis_type)
    )
    existing_bookmark = session.exec(existing_statement).one_or_none()
    if existing_bookmark is not None:
        response.status_code = 200
        return SuccessResponse(
            message="Bookmark already exists."
        )
    try:
        new_bookmark = AnalysisBookmark(
            user_id=payload.sub,
            analysis_type=analysis_type,
            analysis_id=analysis_id
        )
        session.add(new_bookmark)
        session.commit()
        session.refresh(new_bookmark)
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
    response.status_code = 200
    return SuccessResponse(
        message="Bookmark added."
    )

@analysis_router.delete("/bookmarks/{analysis_id}")
async def remove_bookmark(analysis_id: UUID, session: SessionDep, response: Response, payload: Annotated[AccessTokenPayload, Depends(check_auth)]):
    statement = (
        select(AnalysisBookmark)
        .where(AnalysisBookmark.user_id == payload.sub)
        .where(AnalysisBookmark.analysis_id == analysis_id)
    )
    result = session.exec(statement).one_or_none()
    if result is None:
        raise AppException(
            404,
            ErrorResponse(
                code=ErrorResponseCode.NOT_FOUND,
                message="Bookmark not found"
            )
        )
    try:
        session.delete(result)
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
        message="Bookmark removed."
    )

