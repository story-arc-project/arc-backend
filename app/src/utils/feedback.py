from typing import Any, Optional

from src.api.models.base import ErrorResponse
from src.api.models.exc import AppException
from src.enums import ErrorResponseCode

ALLOWED_CAMPAIGN_IDS = {"analysis-satisfaction"}
ALLOWED_CONTEXT_KEYS = {"analysis_id", "analysis_type"}
ALLOWED_CONTEXT_ANALYSIS_TYPES = {"comprehensive", "keyword"}

def validate_campaign_id(campaign_id: str):
    if campaign_id not in ALLOWED_CAMPAIGN_IDS:
        raise AppException(
            status_code = 400,
            error = ErrorResponse(
                code = ErrorResponseCode.BAD_REQUEST,
                message = "campaign_id is invalid."
            )
        )
    return campaign_id

def filter_context(context: Optional[dict[str, Any]]):
    filtered_context = None
    if context is not None:
        filtered_context = {
            key: value
            for key, value in context.items()
            if key in ALLOWED_CONTEXT_KEYS
        }
    if filtered_context is not None and "analysis_type" in filtered_context:
        analysis_type = filtered_context["analysis_type"]
        if analysis_type not in ALLOWED_CONTEXT_ANALYSIS_TYPES:
            raise AppException(
                status_code = 400,
                error = ErrorResponse(
                    code = ErrorResponseCode.BAD_REQUEST,
                    message = "analysis_type is invalid."
                )
            )
    return filtered_context