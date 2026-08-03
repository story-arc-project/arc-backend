from src.api.models.base import ErrorResponse
from src.api.models.exc import AppException
from src.enums import ErrorResponseCode

ALLOWED_CAMPAIGN_IDS = {"analysis-satisfaction"}

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