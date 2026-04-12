from datetime import date
from typing import Any
from pydantic import BaseModel, EmailStr, field_validator

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
    phone: str
    education: str
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