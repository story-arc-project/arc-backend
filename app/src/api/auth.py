from datetime import datetime, timezone
from typing import Annotated
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel
from sqlmodel import select

from src.utils.auth import check_auth
from src.utils.cors import check_cors
from src.utils.oauth import google_login
from src.const import ACCESS_TOKEN_KEY, LOGIN_REDIRECT_ENDPOINT_PREFIX, REFRESH_TOKEN_KEY
from src.utils.verify import send_code, verify_code
from src.api.models.base import ErrorResponse, LoginData, OnboardResponseData, RefreshData, UserInfo
from src.api.models.request import LoginRequest, OnboardRequest, SignupRequest, SocialLoginRequest, VerificationRequest, VerifyCodeRequest
from src.api.models.response import LoginResponse, OnboardResponse, RefreshResponse, SignupResponse, VerificationSentResponse
from src.db.db import SessionDep
from src.db.models import OauthAccount, Token, User, UserProfile
from src.enums import ErrorResponseCode, JWTTokenStatus, OauthProviderId, UserStatus
from src.utils.pwd import hash_password, verify_password
from src.utils.token import AccessTokenPayload, create_access_token, create_refresh_token, hash_jti, verify_refresh_token

auth_router = APIRouter()

ACCESS_TOKEN_PATH = "/"
REFRESH_TOKEN_PATH = "/auth/refresh"

class SetTokenResult(BaseModel):
    acc_exp: datetime
    ref_exp: datetime
    ref_iat: datetime
    jti: str
    id: int

def set_tokens(user_id: int, response: Response, session: SessionDep):
    ref = create_refresh_token(str(user_id))
    response.set_cookie(
        key=REFRESH_TOKEN_KEY,
        value=ref.token,
        httponly=True,
        secure=True,
        samesite="none",
        path=REFRESH_TOKEN_PATH,
        expires=ref.exp
    )
    acc = create_access_token(str(user_id), ref.jti)
    response.set_cookie(
        key=ACCESS_TOKEN_KEY,
        value=acc.token,
        httponly=True,
        secure=True,
        samesite="none",
        path=ACCESS_TOKEN_PATH,
        expires=acc.exp
    )
    new_ref = Token(
        jti_hash = hash_jti(ref.jti),
        user_id = user_id,
        iat = ref.iat,
        exp = ref.exp
    )
    session.add(new_ref)
    session.commit()
    session.refresh(new_ref)
    return SetTokenResult(
        acc_exp = acc.exp,
        ref_exp = ref.exp,
        ref_iat = ref.iat,
        jti = ref.jti,
        id = new_ref.id
    )

def remove_tokens(response: Response):
    response.set_cookie(
        key=ACCESS_TOKEN_KEY,
        value="",
        max_age=0,
        path=ACCESS_TOKEN_PATH
    )
    response.set_cookie(
        key=REFRESH_TOKEN_KEY,
        value="",
        max_age=0,
        path=REFRESH_TOKEN_PATH
    )

def get_login_response(session: SessionDep, response: Response, result: User, message: str, status_code: int = 200):
    onboarded = session.exec(select(UserProfile).where(UserProfile.user_id == result.id)).first() is not None
    res = set_tokens(result.id, response, session)
    response.status_code = status_code
    return LoginResponse(
        message = message,
        data = LoginData(
            user = UserInfo(
                email = result.email
            ),
            onboarded = onboarded,
            expire_at = res.acc_exp
        )
    )

@auth_router.post("/signup")
async def signup(body: SignupRequest, session: SessionDep, response: Response):
    statement = select(User).where(User.email == body.email)
    if session.exec(statement).one_or_none() is not None:
        response.status_code = 409
        return ErrorResponse(
            code = ErrorResponseCode.EMAIL_ALREADY_EXISTS,
            message = "This email is already registered."
        )
    # TODO: Add weak password detection
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
    # TODO: Add account lock when too many requests
    return get_login_response(session, response, result, "Login successful")

@auth_router.post("/resend-verification")
async def send_verification(body: VerificationRequest, session: SessionDep, response: Response):
    # TODO: Add rate limit
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

@auth_router.post("/verify-email")
async def verify(body: VerifyCodeRequest, session: SessionDep, response: Response):
    statement = select(User).where(User.email == body.email)
    result = session.exec(statement).one_or_none()
    if result is None or not verify_code(body.email, body.code):
        response.status_code = 401
        return ErrorResponse(
            code = ErrorResponseCode.INVALID_CODE,
            message = "The verification code is incorrect."
        )
    result.status = UserStatus.VERIFIED
    session.add(result)
    session.commit()
    session.refresh(result)
    return get_login_response(session, response, result, "Email verified successfully. You have been logged in.")

@auth_router.post("/social-login")
async def social_login(request: Request, body: SocialLoginRequest, session: SessionDep, response: Response):
    origin = check_cors(request)
    if origin is None:
        response.status_code = 403
        return ErrorResponse(
            code = ErrorResponseCode.CORS_NOT_ALLOWED,
            message = "Origin not allowed"
        )
    res = google_login(
        code = body.token,
        redirect_uri = origin + LOGIN_REDIRECT_ENDPOINT_PREFIX + OauthProviderId.GOOGLE
    )
    if res is None:
        response.status_code = 401
        return ErrorResponse(
            code = ErrorResponseCode.SOCIAL_AUTH_FAILED,
            message = "Could not verify social credentials with Google."
        )
    id: str | None = res.get("sub")
    email: str | None = res.get("email")
    is_email_verified: bool | None = res.get("email_verified")
    if id is None or email is None or is_email_verified is None or not is_email_verified:
        response.status_code = 401
        return ErrorResponse(
            code = ErrorResponseCode.SOCIAL_AUTH_FAILED,
            message = "Could not verify social credentials with Google."
        )

    statement = select(OauthAccount).where(
        OauthAccount.provider == OauthProviderId.GOOGLE,
        OauthAccount.provider_user_id == id
    )
    _oauth = session.exec(statement).one_or_none()
    new = False
    if _oauth is None:
        statement = select(User).where(User.email == email)
        result = session.exec(statement).one_or_none()
        if result is None:
            new = True
            result = User(
                email = email,
                password_hash = None
            )
            session.add(result)
            session.commit()
            session.refresh(result)
        if result.id is None:
            raise RuntimeError("User ID missing after flush")
        _oauth = OauthAccount(
            user_id = result.id,
            provider = OauthProviderId.GOOGLE,
            provider_user_id = id
        )
    else:
        result = session.get(User, _oauth.user_id)
        if result is None:
            raise RuntimeError("User missing from foreign key")

    if result.status != UserStatus.VERIFIED:
        result.status = UserStatus.VERIFIED
        session.add(result)

    session.add(_oauth)
    session.commit()

    if new:
        return get_login_response(session, response, result, "Account created", 201)
    else:
        return get_login_response(session, response, result, "Login successful")

@auth_router.post("/refresh")
async def refresh(request: Request, session: SessionDep, response: Response):
    refresh_token = request.cookies.get(REFRESH_TOKEN_KEY)
    if refresh_token is None:
        response.status_code = 401
        return ErrorResponse(
            code = ErrorResponseCode.AUTH_MISSING_COOKIES,
            message = "Cookies missing."
        )
    payload = verify_refresh_token(refresh_token)
    if payload == JWTTokenStatus.EXPIRED:
        response.status_code = 401
        remove_tokens(response)
        return ErrorResponse(
            code = ErrorResponseCode.AUTH_TOKEN_EXPIRED,
            message = "Refresh token expired."
        )
    if payload == JWTTokenStatus.INVALID:
        response.status_code = 401
        remove_tokens(response)
        return ErrorResponse(
            code = ErrorResponseCode.AUTH_TOKEN_INVALID,
            message = "Invalid refresh token."
        )
    statement = select(Token).where(Token.jti_hash == hash_jti(payload.jti))
    result = session.exec(statement).one_or_none()
    if result is None:
        response.status_code = 401
        remove_tokens(response)
        return ErrorResponse(
            code = ErrorResponseCode.AUTH_TOKEN_INVALID,
            message = "Invalid refresh token."
        )
    if result.revoked:
        response.status_code = 403
        remove_tokens(response)
        return ErrorResponse(
            code = ErrorResponseCode.AUTH_REVOKED,
            message = "Refresh token revoked."
        )
    if result.next is not None:
        response.status_code = 403
        remove_tokens(response)
        return ErrorResponse(
            code = ErrorResponseCode.AUTH_REUSE_DETECTED,
            message = "Refresh token rotated."
        )
    if result.exp < datetime.now(timezone.utc):
        response.status_code = 401
        remove_tokens(response)
        return ErrorResponse(
            code = ErrorResponseCode.AUTH_TOKEN_EXPIRED,
            message = "Refresh token expired."
        )
    set_token_res = set_tokens(result.user_id, response, session)
    result.next = set_token_res.id
    session.add(result)
    session.commit()
    response.status_code = 200
    return RefreshResponse(
        data = RefreshData(
            expire_at = set_token_res.acc_exp
        )
    )

@auth_router.post("/onboarding")
async def onboard(body: OnboardRequest, session: SessionDep, response: Response, payload: Annotated[AccessTokenPayload, Depends(check_auth)]):
    user_id = int(payload.sub)
    statement = select(UserProfile).where(UserProfile.user_id == user_id)
    user_profile = session.exec(statement).one_or_none()
    if user_profile is not None:
        # TODO: Do something
        response.status_code = 400
        return ErrorResponse(
            code = ErrorResponseCode.DUPLICATE_ONBOARDING,
            message = "Onboarding data already exists."
        )
    user_profile = UserProfile(
        user_id = user_id,
        name = body.name,
        birth = body.birth,
        phone = body.phone,
        education = body.education,
        worry = body.worry,
        interest = body.interest
    )
    session.add(user_profile)
    session.commit()
    response.status_code = 200
    return OnboardResponse(
        message = "Onboarding completed successfully.",
        data = OnboardResponseData(
            onboarded = True
        )
    )