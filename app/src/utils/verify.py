import secrets

from pydantic import EmailStr, BaseModel, Field
from typing import Literal, Annotated, Union

from src.utils.mail import send_mail
from src.const import VERIFICATION_CODE_EXPIRE, VERIFICATION_MAX_ATTEMPTS
from src.db.red import get_code, store_code, PURPOSE_SCOPE
from src.utils.ratelimit import RateLimiter
from src.api.models.base import ErrorResponse, ErrorResponseCode

class UnverifiedState(BaseModel):
    is_verified: Literal[False] = False
    remaining_attempts: int
    is_expired: bool

class VerifiedState(BaseModel):
    is_verified: Literal[True] = True

VerificationState = Annotated[
    Union[UnverifiedState, VerifiedState],
    Field(discriminator="is_verified")
]

custom_locked_exception = ErrorResponse(
    code = ErrorResponseCode.TOO_MANY_ATTEMPTS,
    message = "Too many attempts. Please request a new code."
)

def __generate_code():
    return str(secrets.randbelow(900000) + 100000)

def _generate_code(email: EmailStr, purpose: PURPOSE_SCOPE):
    code = __generate_code()
    store_code(email, code, purpose)
    return code

def verify_code(email: str, user_code: str, purpose: PURPOSE_SCOPE = "verify", delete: bool = True) -> VerificationState:
    limiter = RateLimiter(None, email, f"send:{purpose}", VERIFICATION_CODE_EXPIRE, VERIFICATION_MAX_ATTEMPTS, custom_locked_exception)
    stored_code = get_code(email, purpose)

    if not stored_code or stored_code != user_code:
        current_attempts = limiter.record_failure()["email"]
        return UnverifiedState(remaining_attempts=VERIFICATION_MAX_ATTEMPTS-current_attempts, is_expired=(not stored_code))
    
    if delete:
        limiter.clear()
    return VerifiedState()

def send_code(email: EmailStr, purpose: PURPOSE_SCOPE = "verify"):
    RateLimiter(None, email, f"send:{purpose}", VERIFICATION_CODE_EXPIRE, VERIFICATION_MAX_ATTEMPTS, custom_locked_exception, True)
    code = _generate_code(email, purpose)
    return send_mail(
        email,
        "ARC verification code",
        code
    )