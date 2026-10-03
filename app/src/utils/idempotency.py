from typing import Literal

from src.enums import AnalysisType


type ReserveIdempotencyKey = str

def get_reserve_idempotency_key(idempotency_key_original: str, analysis_type: AnalysisType | Literal["cover_letter"]) -> ReserveIdempotencyKey:
    analysis_type_str = analysis_type.value if isinstance(analysis_type, AnalysisType) else analysis_type
    return f"reserve:{analysis_type_str}:{idempotency_key_original}"