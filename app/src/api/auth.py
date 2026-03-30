from fastapi import APIRouter, Response
from sqlmodel import select

from app.src.api.models.base import ErrorResponse, LoginData, UserInfo
from app.src.api.models.request import LoginRequest
from app.src.api.models.response import LoginResponse
from app.src.db.db import SessionDep
from app.src.db.models import User, UserProfile
from app.src.enums import ErrorResponseCode, UserStatus
from app.src.utils.pwd import verify_password
from app.src.utils.token import create_access_token

router = APIRouter()

@router.post("/auth/login")
async def login(body: LoginRequest, session: SessionDep, response: Response):
    statement = select(User).where(User.email == body.email)
    result = session.exec(statement).one_or_none()
    if result is None or result.password_hash is None or not verify_password(body.password, result.password_hash):
        return ErrorResponse(
            code = ErrorResponseCode.INVALID_CREDENTIALS,
            message = "The email or password is incorrect."
        )
    if result.status == UserStatus.UNVERIFIED:
        return ErrorResponse(
            code = ErrorResponseCode.EMAIL_NOT_VERIFIED,
            message = "Email verification needed."
        )
    # Add account lock when too many requests
    onboarded = session.exec(select(UserProfile).where(UserProfile.user_id == result.id)).first() is not None
    access_token, acc_exp = create_access_token(str(result.id))
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=True,
        samesite="strict",
        path="/",
        expires=int(acc_exp.timestamp())
    )
    return LoginResponse(
        message = "Login successful",
        data = LoginData(
            user = UserInfo(
                email = result.email
            ),
            onboarded = onboarded,
            expire_at = acc_exp
        )
    )