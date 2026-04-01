from fastapi import APIRouter, Response
from sqlmodel import select

from src.utils.verify import send_code
from src.api.models.base import ErrorResponse, LoginData, UserInfo
from src.api.models.request import LoginRequest, SignupRequest, VerificationRequest
from src.api.models.response import LoginResponse, SignupResponse, VerificationSentResponse
from src.db.db import SessionDep
from src.db.models import User, UserProfile
from src.enums import ErrorResponseCode, UserStatus
from src.utils.pwd import hash_password, verify_password
from src.utils.token import create_access_token

auth_router = APIRouter()

@auth_router.post("/signup")
async def signup(body: SignupRequest, session: SessionDep, response: Response):
    statement = select(User).where(User.email == body.email)
    if session.exec(statement).one_or_none() is not None:
        response.status_code = 409
        return ErrorResponse(
            code = ErrorResponseCode.EMAIL_ALREADY_EXISTS,
            message = "This email is already registered."
        )
    # Add weak password detection
    password_hash = hash_password(body.password)
    user = User(
        email = body.email,
        password_hash = password_hash
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    errors = send_code(body.email)
    if errors:
        response.status_code = 500
        return ErrorResponse(
            code = ErrorResponseCode.SERVER_ERROR,
            message = "Server side error. Please check logs."
        )
    response.status_code = 201
    return SignupResponse(
        message = "Email verification needed."
    )

@auth_router.post("/login")
async def login(body: LoginRequest, session: SessionDep, response: Response):
    statement = select(User).where(User.email == body.email)
    result = session.exec(statement).one_or_none()
    if result is None or result.password_hash is None or not verify_password(body.password, result.password_hash):
        response.status_code = 401
        return ErrorResponse(
            code = ErrorResponseCode.INVALID_CREDENTIALS,
            message = "The email or password is incorrect."
        )
    if result.status == UserStatus.UNVERIFIED:
        response.status_code = 403
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
    response.status_code = 200
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

@auth_router.post("/resend-verification")
async def send_verification(body: VerificationRequest, session: SessionDep, response: Response):
    # Add rate limit
    statement = select(User).where(User.email == body.email)
    result = session.exec(statement).one_or_none()
    if result is None:
        response.status_code = 200
        return VerificationSentResponse()
    if result.status == UserStatus.VERIFIED:
        response.status_code = 400
        return ErrorResponse(
            code = ErrorResponseCode.ALREADY_VERIFIED,
            message = "This account is already verified. Please log in."
        )
    errors = send_code(result.email)
    if errors:
        response.status_code = 500
        return ErrorResponse(
            code = ErrorResponseCode.SERVER_ERROR,
            message = "Server side error. Please check logs."
        )
    response.status_code = 200
    return VerificationSentResponse()