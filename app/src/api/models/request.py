from datetime import date
from typing import Annotated, Any
from uuid import UUID
from pydantic import BaseModel, EmailStr, field_validator, model_validator, AfterValidator
import re

from src.enums import Affiliation
from src.api.models.consent import AGREEABLE_CONSENT_VERSIONS, CONSENT_REQUIRED

def validate_password(v: str):
    if len(v) < 8:
        raise ValueError("WEAK_PASSWORD")
    if len(v) > 128:
        raise ValueError("WEAK_PASSWORD")
    if not re.search(r"[A-Za-z]", v):
        raise ValueError("WEAK_PASSWORD")
    if not re.search(r"[0-9]", v):
        raise ValueError("WEAK_PASSWORD")
    return v

ValidPassword = Annotated[str, AfterValidator(validate_password)]

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class SignupRequest(BaseModel):
    email: EmailStr
    password: ValidPassword

class VerificationRequest(BaseModel):
    email: EmailStr

class VerifyCodeRequest(BaseModel):
    email: EmailStr
    code: str

class SocialLoginRequest(BaseModel):
    provider: str = "google" # TODO: restrict to google for now
    token: str

class OnboardRequest(BaseModel):
    name: str
    birth: date
    affiliation: Affiliation
    school: str | None = None
    department: str | None = None
    company: str | None = None
    desiredRole: str | None = None
    affiliationDetail: str | None = None
    phone: str
    worry: list[str]
    interest: list[str]

    @field_validator("name", mode="after")
    @classmethod
    def validate_name(cls, v: str):
        if len(v) == 0:
            raise ValueError("Name must not be empty")
        return v

    @field_validator("birth", mode="before")
    @classmethod
    def validate_birth(cls, v):
        if not isinstance(v, str):
            raise ValueError("Birth must be a string")
        try:
            d = date.fromisoformat(v)
        except ValueError:
            raise ValueError("Birth must be a valid YYYY-MM-DD date")
        if d > date.today():
            raise ValueError("Birth must be a past date")
        return d
    
    @field_validator("phone", mode="after")
    @classmethod
    def validate_phone(cls, v: str):
        if len(v) != 11:
            raise ValueError("Phone number must be 11 digits")
        if not v.isdigit():
            raise ValueError("Phone number must contain digits only")
        return v

    @model_validator(mode="after")
    def validate_affiliation_fields(self):
        if self.affiliation == Affiliation.STUDENT:
            if self.company or self.desiredRole or self.affiliationDetail:
                raise ValueError("student can only have school and department")
        elif self.affiliation == Affiliation.EMPLOYED:
            if self.school or self.department or self.desiredRole or self.affiliationDetail:
                raise ValueError("employed can only have company")
        elif self.affiliation == Affiliation.JOBSEEKER:
            if self.school or self.department or self.company or self.affiliationDetail:
                raise ValueError("jobseeker can only have desiredRole")
        elif self.affiliation == Affiliation.OTHER:
            if self.school or self.department or self.company or self.desiredRole:
                raise ValueError("other can only have affiliationDetail")
        return self

class ProfilePatchRequest(BaseModel):
    name: str | None = None
    birth: date | None = None
    affiliation: Affiliation | None = None
    school: str | None = None
    department: str | None = None
    company: str | None = None
    desiredRole: str | None = None
    affiliationDetail: str | None = None
    phone: str | None = None
    worry: list[str] | None = None
    interest: list[str] | None = None

    @field_validator("name", mode="after")
    @classmethod
    def validate_name(cls, v: str | None):
        if isinstance(v, str) and len(v) == 0:
            raise ValueError("Name must not be empty")
        return v

    @field_validator("birth", mode="before")
    @classmethod
    def validate_birth(cls, v):
        if v is None:
            return v
        if not isinstance(v, str):
            raise ValueError("Birth must be a string")
        try:
            d = date.fromisoformat(v)
        except ValueError:
            raise ValueError("Birth must be a valid YYYY-MM-DD date")
        if d > date.today():
            raise ValueError("Birth must be a past date")
        return d
    
    @field_validator("phone", mode="after")
    @classmethod
    def validate_phone(cls, v: str | None):
        if v is None:
            return v
        if len(v) != 11:
            raise ValueError("Phone number must be 11 digits")
        if not v.isdigit():
            raise ValueError("Phone number must contain digits only")
        return v

    @model_validator(mode="after")
    def validate_affiliation_fields(self):
        if self.affiliation is None and not (self.school or self.department or self.company or self.desiredRole or self.affiliationDetail):
            return self
        if self.affiliation == Affiliation.STUDENT:
            if self.company or self.desiredRole or self.affiliationDetail:
                raise ValueError("student can only have school and department")
        elif self.affiliation == Affiliation.EMPLOYED:
            if self.school or self.department or self.desiredRole or self.affiliationDetail:
                raise ValueError("employed can only have company")
        elif self.affiliation == Affiliation.JOBSEEKER:
            if self.school or self.department or self.company or self.affiliationDetail:
                raise ValueError("jobseeker can only have desiredRole")
        elif self.affiliation == Affiliation.OTHER:
            if self.school or self.department or self.company or self.desiredRole:
                raise ValueError("other can only have affiliationDetail")
        return self

class ExperiencePostRequest(BaseModel):
    type: str
    content: dict[str, Any]
    importance: int | None = None

    @field_validator("type", mode="after")
    @classmethod
    def validate_type(cls, v: str):
        if len(v) == 0:
            raise ValueError("Type must not be empty")
        return v
    
    @field_validator("importance", mode="after")
    @classmethod
    def validate_importance(cls, v: int | None):
        if isinstance(v, int) and (v < 1 or v > 5):
            raise ValueError("Importance must be between 1 and 5")
        return v

class ExperiencePutRequest(BaseModel):
    content: dict[str, Any]
    importance: int | None
    
    @field_validator("importance", mode="after")
    @classmethod
    def validate_importance(cls, v: int | None):
        if isinstance(v, int) and (v < 1 or v > 5):
            raise ValueError("Importance must be between 1 and 5")
        return v

class ExperiencePatchRequest(BaseModel):
    importance: int | None
    
    @field_validator("importance", mode="after")
    @classmethod
    def validate_importance(cls, v: int | None):
        if isinstance(v, int) and (v < 1 or v > 5):
            raise ValueError("Importance must be between 1 and 5")
        return v

class LibraryPostRequest(BaseModel):
    name: str
    color: str
    icon: str
    is_system: bool = False
    filter: dict[str, Any] | None

    @field_validator("name", mode="after")
    @classmethod
    def validate_name(cls, v: str):
        if len(v) == 0:
            raise ValueError("Name must not be empty")
        return v

class ComprehensiveAnalysisPostRequest(BaseModel):
    experiences: list[UUID]

class KeywordAnalysisPostRequest(BaseModel):
    keywords: list[str]

class ResumePostRequest(BaseModel):
    language: str

class UserDeleteByPasswordRequest(BaseModel):
    password: str

class UserDeleteByTokenRequest(BaseModel):
    token: str

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(VerifyCodeRequest):
    newPassword: ValidPassword

class VersionedConsent(BaseModel):
    version: str
    granted: bool

class Age14Consent(BaseModel):
    granted: bool

class Agreements(BaseModel):
    termsOfService: VersionedConsent
    privacyRequired: VersionedConsent
    age14: Age14Consent
    personalizedService: VersionedConsent
    marketing: VersionedConsent

    @model_validator(mode="after")
    def validate_required_consents(self) -> "Agreements":
        for field, required in CONSENT_REQUIRED.items():
            value = getattr(self, field)
            if required and (value is None or not value.granted):
                raise ValueError(f"{field} is required and must be granted")
        for field, agreeable_version in AGREEABLE_CONSENT_VERSIONS.items():
            value = getattr(self, field)
            if value is None or value.version != agreeable_version:
                raise ValueError(f"{field} has wrong version")
        return self

    def iter_consents(self) -> list[tuple[str, VersionedConsent | Age14Consent]]:
        return [(name, getattr(self, name)) for name in Agreements.model_fields]

class UserConsentRequest(BaseModel):
    agreements: Agreements