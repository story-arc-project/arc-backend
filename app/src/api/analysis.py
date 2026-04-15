from typing import Annotated
from fastapi import APIRouter, Depends, Response
from sqlmodel import select

from src.api.models.base import IndividualAnalysisList, IndividualAnalysisListData
from src.api.models.response import IndividualAnalysisListResponse
from src.db.db import SessionDep
from src.db.models import Experience, IndividualAnalysis
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