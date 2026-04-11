from datetime import date, datetime
from uuid import UUID
from pydantic import BaseModel, EmailStr
from typing import Any, Generic, TypeVar

from src.enums import ErrorResponseCode, ExperiencePriority, OauthProviderId

T = TypeVar("T")

class SuccessResponse(BaseModel):
    status: str = "success"
    message: str

class SuccessResponseWithData(SuccessResponse, Generic[T]):
    data: T

class ErrorResponse(BaseModel):
    status: str = "error"
    code: ErrorResponseCode
    message: str

class UserInfo(BaseModel):
    email: EmailStr

class LoginData(BaseModel):
    user: UserInfo
    onboarded: bool
    expire_at: datetime

class RefreshData(BaseModel):
    expire_at: datetime

class OnboardResponseData(BaseModel):
    onboarded: bool

class AccountData(BaseModel):
    email: EmailStr
    has_password: bool
    email_verified: bool
    connected_oauth: list[OauthProviderId]

class ProfileData(BaseModel):
    name: str
    birth: date
    phone: str
    education: str
    worry: list[str]
    interest: list[str]

class AuthMeData(BaseModel):
    account: AccountData
    profile: ProfileData | None
    onboarded: bool
    # TODO: validate profile is None only when onboarded is False, not None only when onboarded is True

class UUIDData(BaseModel):
    id: UUID

class ExperienceResponseData(BaseModel):
    id: UUID
    user_id: UUID
    type: str
    priority: ExperiencePriority
    content: dict[str, Any]
    created_at: datetime
    updated_at: datetime

class ExperiencesResponseData(BaseModel):
    count: int
    contents: list[ExperienceResponseData]

class LibraryResponseData(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    color: str
    icon: str
    filter: dict[str, Any]
    sort_order: int
    created_at: datetime
    updated_at: datetime

class LibraryContentData(BaseModel):
    system: list[LibraryResponseData]
    custom: list[LibraryResponseData]

class LibrariesResponseData(BaseModel):
    count: int
    contents: LibraryContentData