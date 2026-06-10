import secrets

from pydantic import EmailStr, BaseModel, Field
from typing import Literal, Annotated, Union

from src.utils.mail import send_mail
from src.db.red import delete_code, get_code, store_code, decr_limit, PURPOSE_SCOPE

class UnverifiedState(BaseModel):
    is_verified: Literal[False] = False
    remaining_attempts: int

class VerifiedState(BaseModel):
    is_verified: Literal[True] = True
    remaining_attempts: None = None

VerificationState = Annotated[
    Union[UnverifiedState, VerifiedState],
    Field(discriminator="is_verified")
]

def __generate_code():
    return str(secrets.randbelow(900000) + 100000)

def _generate_code(email: EmailStr, purpose: PURPOSE_SCOPE):
    code = __generate_code()
    store_code(email, code, purpose)
    return code

def verify_code(email: str, user_code: str, purpose: PURPOSE_SCOPE = "verify") -> VerificationState:
    stored_code = get_code(email, purpose)

    if not stored_code or stored_code != user_code:
        return UnverifiedState(remaining_attempts=decr_limit(email, purpose))
    
    delete_code(email, purpose)
    return VerifiedState()

def send_code(email: EmailStr, purpose: PURPOSE_SCOPE = "verify"):
    code = _generate_code(email, purpose)
    return send_mail(
        email,
        "ARC verification code",
        code
    )