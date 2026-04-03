from datetime import date
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

    @field_validator("birth", mode="before")
    @classmethod
    def validate_date_format(cls, v: str):
        try:
            return date.fromisoformat(v)
        except ValueError:
            raise ValueError("Must be a valid YYYY-MM-DD date")
    
    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str):
        if len(v) != 11:
            raise ValueError("Phone number must be 11 digits")
        if not v.isdigit():
            raise ValueError("Phone number must contain digits only")
        return v