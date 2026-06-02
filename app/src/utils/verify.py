import secrets

from pydantic import EmailStr, BaseModel, Field
from typing import Literal, Annotated, Union

from src.utils.mail import send_mail
from src.db.red import delete_code, get_code, store_code, decr_limit

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

def _generate_code(email: EmailStr):
    code = __generate_code()
    store_code(email, code)
    return code

def verify_code(email: str, user_code: str) -> VerificationState:
    stored_code = get_code(email)

    if not stored_code or stored_code != user_code:
        return UnverifiedState(remaining_attempts=decr_limit(email))
    
    delete_code(email)
    return VerifiedState()

def send_code(email: EmailStr):
    code = _generate_code(email)
    return send_mail(
        email,
        "ARC verification code",
        code
    )