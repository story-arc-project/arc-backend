import traceback
import requests
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, Response
from sqlmodel import col, select, and_
import json

from src.api.models.base import BookmarkData, ComprehensiveAnalysisData, ComprehensiveAnalysisExperienceData, ComprehensiveAnalysisList, ComprehensiveAnalysisListData, ErrorResponse, IndividualAnalysisData, IndividualAnalysisList, IndividualAnalysisListData, SuccessResponse, KeywordAnalysisList, KeywordAnalysisListData, KeywordAnalysisData, UUIDData
from src.api.models.exc import AppException
from src.api.models.request import ComprehensiveAnalysisPostRequest, KeywordAnalysisPostRequest
from src.api.models.response import BookmarkListResponse, ComprehensiveAnalysisListResponse, ComprehensiveAnalysisResponse, DeleteSuccessResponse, IndividualAnalysisListResponse, IndividualAnalysisResponse, KeywordAnalysisListResponse, KeywordAnalysisResponse, PostSuccessResponse
from src.db.db import SessionDep
from src.db.models import AnalysisBookmark, ComprehensiveAnalysis, Experience, IndividualAnalysis, KeywordAnalysis, UserProfile
from src.enums import AnalysisType, ErrorResponseCode
from src.utils.auth import check_auth
from src.utils.ratelimit import analysis_rate_limiters
from src.utils.token import AccessTokenPayload

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

@analysis_router.post("/comprehensive")
async def post_comprehensive_analysis(
    body: ComprehensiveAnalysisPostRequest,
    session: SessionDep,
    response: Response,
    payload: Annotated[AccessTokenPayload, Depends(check_auth)],
    _user_limit: Annotated[None, Depends(analysis_rate_limiters["comprehensive"]["user"])],
    _ip_limit: Annotated[None, Depends(analysis_rate_limiters["comprehensive"]["ip"])]
):
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
    try:
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
    return PostSuccessResponse(
        message = "Queued new comprehensive analysis.",
        data = UUIDData(
            id = new_comprehensive_analysis.id
        )
    )

def get_experience_titles(session: SessionDep, experience_ids: set[UUID]):
    if len(experience_ids) == 0:
        print("experience_ids length is 0")
        raise AppException(
            500,
            ErrorResponse(
                code = ErrorResponseCode.SERVER_ERROR,
                message = "Internal server error"
            )
        )
    experience_titles: dict[UUID, str] = {}
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
                title = f"{[title for title in [experience_titles.get(exp_id) for exp_id in analysis.experience_ids] if title is not None][0]} 외 {len(analysis.experience_ids)-1}개"
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
            title = f"{list(experience_titles.values())[0]} 외 {len(experience_ids)-1}개"
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
async def post_keyword_analysis(
    body: KeywordAnalysisPostRequest,
    session: SessionDep,
    response: Response,
    payload: Annotated[AccessTokenPayload, Depends(check_auth)],
    _user_limit: Annotated[None, Depends(analysis_rate_limiters["keyword"]["user"])],
    _ip_limit: Annotated[None, Depends(analysis_rate_limiters["keyword"]["ip"])]
):
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
            "keywords": body.keywords,
            "target": "" # TODO: Connect target to API
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
    return PostSuccessResponse(
        message = "Queued new keyword analysis.",
        data = UUIDData(
            id = new_keyword_analysis.id
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
                created_at = analysis.created_at,
                updated_at = analysis.updated_at,
                is_bookmarked = (bookmark is not None),
                title = f"{", ".join(analysis.keywords)} 분석"
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
            result = analysis.result,
            created_at = analysis.created_at,
            updated_at = analysis.updated_at,
            is_bookmarked = (bookmark is not None),
            title = f"{", ".join(analysis.keywords)} 분석"
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
    return BookmarkListResponse(
        message = "Fetch success.",
        data = [BookmarkData(
            id = bookmark.analysis_id,
            type = bookmark.analysis_type,
            created_at = bookmark.created_at,
            updated_at = bookmark.updated_at
        ) for bookmark in result]
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