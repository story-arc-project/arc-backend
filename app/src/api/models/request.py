from datetime import date
from typing import Any
from pydantic import BaseModel, EmailStr, field_validator, model_validator

from src.enums import Affiliation

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class SignupRequest(BaseModel):
    email: EmailStr
    password: str

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
    school: str | None
    department: str | None
    company: str | None
    desiredRole: str | None
    affiliationDetail: str | None
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

class ExperiencePostRequest(BaseModel):
    type: str
    content: dict[str, Any]

    @field_validator("type", mode="after")
    @classmethod
    def validate_type(cls, v: str):
        if len(v) == 0:
            raise ValueError("Type must not be empty")
        return v

class ExperiencePutRequest(BaseModel):
    content: dict[str, Any]

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