from datetime import date, datetime
from uuid import UUID
from pydantic import BaseModel, EmailStr, ConfigDict
from typing import Any, Generic, Literal, TypeVar

from src.enums import Affiliation, AnalysisStatus, AnalysisType, ErrorResponseCode, OauthProviderId

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

class EmailVerificationErrorResponse(ErrorResponse):
    remaining_attempts: int

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
    affiliation: Affiliation
    school: str | None
    department: str | None
    company: str | None
    desiredRole: str | None
    affiliationDetail: str | None
    phone: str
    worry: list[str]
    interest: list[str]

class AuthMeData(BaseModel):
    account: AccountData
    profile: ProfileData | None
    onboarded: bool
    # TODO: validate profile is None only when onboarded is False, not None only when onboarded is True

class UUIDData(BaseModel):
    id: UUID

class UUIDDataWithTitle(UUIDData):
    title: str

class UUIDDataWithTitleNone(UUIDData):
    title: str | None

class ExperienceResponseData(BaseModel):
    id: UUID
    user_id: UUID
    type: str
    importance: int | None
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
    filter: dict[str, Any] | None
    sort_order: int
    created_at: datetime
    updated_at: datetime

class LibraryContentData(BaseModel):
    system: list[LibraryResponseData]
    custom: list[LibraryResponseData]

class LibrariesResponseData(BaseModel):
    count: int
    contents: LibraryContentData

class PresetResponseData(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    description: str | None
    blocks: list[dict[str, Any]]
    is_favorite: bool
    created_at: datetime
    updated_at: datetime

class PresetsResponseData(BaseModel):
    count: int
    contents: list[PresetResponseData]

class IndividualAnalysisData(BaseModel):
    id: UUID
    status: AnalysisStatus
    experience_id: UUID
    title: str
    type: Literal["individual"] = "individual"
    created_at: datetime
    updated_at: datetime
    result: dict[str, Any] | None
    is_bookmarked: bool

class IndividualAnalysisListData(BaseModel):
    id: UUID
    status: AnalysisStatus
    experience_id: UUID
    title: str
    type: Literal["individual"] = "individual"
    created_at: datetime
    updated_at: datetime
    is_bookmarked: bool

class IndividualAnalysisList(BaseModel):
    count: int
    contents: list[IndividualAnalysisListData]

class ComprehensiveAnalysisExperienceData(BaseModel):
    id: UUID
    title: str | None

class ComprehensiveAnalysisData(BaseModel):
    id: UUID
    status: AnalysisStatus
    experiences: list[ComprehensiveAnalysisExperienceData]
    type: Literal["comprehensive"] = "comprehensive"
    created_at: datetime
    updated_at: datetime
    result: dict[str, Any] | None
    is_bookmarked: bool
    title: str

class ComprehensiveAnalysisListData(BaseModel):
    id: UUID
    status: AnalysisStatus
    experiences: list[ComprehensiveAnalysisExperienceData]
    type: Literal["comprehensive"] = "comprehensive"
    created_at: datetime
    updated_at: datetime
    is_bookmarked: bool
    title: str

class ComprehensiveAnalysisList(BaseModel):
    count: int
    contents: list[ComprehensiveAnalysisListData]

class KeywordAnalysisData(BaseModel):
    id: UUID
    status: AnalysisStatus
    keywords: list[str]
    type: Literal["keyword"] = "keyword"
    target: str
    created_at: datetime
    updated_at: datetime
    result: dict[str, Any] | None
    is_bookmarked: bool
    title: str

class KeywordAnalysisListData(BaseModel):
    id: UUID
    status: AnalysisStatus
    keywords: list[str]
    type: Literal["keyword"] = "keyword"
    target: str
    created_at: datetime
    updated_at: datetime
    is_bookmarked: bool
    title: str

class KeywordAnalysisList(BaseModel):
    count: int
    contents: list[KeywordAnalysisListData]

class ResumeListData(BaseModel):
    id: UUID
    title: str | None
    created_at: datetime
    updated_at: datetime

class ResumeList(BaseModel):
    count: int
    contents: list[ResumeListData]

class ResumeData(BaseModel):
    id: UUID
    title: str | None
    created_at: datetime
    updated_at: datetime
    result: dict[str, Any] | None

class PresignUploadData(BaseModel):
    id: UUID
    upload_url: str
    expires_in: int

class FileMetadataPublic(BaseModel):
    id: UUID
    filename: str
    content_type: str
    size: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class BookmarkData(BaseModel):
    id: UUID
    type: AnalysisType
    created_at: datetime
    updated_at: datetime