import hashlib
import hmac
import json
from os import getenv
from sqlmodel import select
from typing import Any
from uuid import UUID
from fastapi import APIRouter, HTTPException, Request, Response

from src.db.db import SessionDep
from src.db.models import IndividualAnalysis
from src.enums import AnalysisStatus

INTERNAL_SECRET_KEY = "INTERNAL_SECRET"

internal_router = APIRouter()

def verify_signature(body: dict[str, Any], signature: str):
    key = getenv(INTERNAL_SECRET_KEY)
    if key is None:
        raise ValueError("Internal secret not set.")
    expected = hmac.new(
        key.encode(),
        json.dumps(body, separators=(",", ":")).encode(),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)

@internal_router.post("/individual/complete")
async def complete_individual(request: Request, session: SessionDep, response: Response):
    body: dict[str, Any] = await request.json()
    signature = request.headers.get("X-Signature")
    if not signature or not verify_signature(body, signature):
        raise HTTPException(status_code=403)
    analysis_id: str | None = body.get("analysis_id")
    result: str | None = body.get("result")
    if analysis_id is None or result is None:
        raise HTTPException(status_code=400)
    statement = select(IndividualAnalysis).where(IndividualAnalysis.id == UUID(analysis_id))
    analysis = session.exec(statement).one_or_none()
    if analysis is None:
        return HTTPException(status_code=404)
    analysis.result = json.loads(result)
    analysis.status = AnalysisStatus.SUCCESS
    session.add(analysis)
    session.commit()
    response.status_code = 200
    return {}