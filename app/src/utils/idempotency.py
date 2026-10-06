from typing import Literal
from uuid import UUID

from fastapi import status
from sqlmodel import col, select

from src.api.models.base import ErrorResponse, UUIDDataWithTitle
from src.api.models.exc import AppException
from src.api.models.response import PostSuccessResponse
from src.db.db import SessionDep
from src.db.models import ComprehensiveAnalysis, CreditReservation, KeywordAnalysis
from src.enums import AnalysisType, CreditReservationStatus, ErrorResponseCode


type ReserveIdempotencyKey = str

def get_reserve_idempotency_key(idempotency_key_original: str, analysis_type: AnalysisType | Literal["cover_letter"]) -> ReserveIdempotencyKey:
    analysis_type_str = analysis_type.value if isinstance(analysis_type, AnalysisType) else analysis_type
    return f"reserve:{analysis_type_str}:{idempotency_key_original}"

def check_idempotency(session: SessionDep, user_id: UUID, idempotency_key: str, analysis_type: AnalysisType | Literal["cover_letter"]):
    existing_reservation = session.exec(
        select(CreditReservation).where(
            CreditReservation.user_id == user_id,
            CreditReservation.idempotency_key == get_reserve_idempotency_key(idempotency_key, analysis_type),
            col(CreditReservation.status).in_([CreditReservationStatus.RESERVED, CreditReservationStatus.CAPTURED]),
        )
    ).first()
    if existing_reservation:
        if analysis_type == AnalysisType.comprehensive:
            stmt = select(ComprehensiveAnalysis).where(
                ComprehensiveAnalysis.reservation_id == existing_reservation.id
            )
        elif analysis_type == AnalysisType.keyword:
            stmt = select(KeywordAnalysis).where(
                KeywordAnalysis.reservation_id == existing_reservation.id
            )
        else:
            return None
        existing_analysis = session.exec(stmt).first()
        if existing_analysis:
            return PostSuccessResponse(
                message="Queued analysis.",
                data=UUIDDataWithTitle(
                    id=existing_analysis.id,
                    title=existing_analysis.title,
                )
            )
        raise AppException(
            status_code=status.HTTP_409_CONFLICT,
            error=ErrorResponse(
                code=ErrorResponseCode.IDEMPOTENCY_KEY_MISMATCH,
                message="A request with this idempotency key is currently being processed. Please wait.",
            ),
        )
    return None