from datetime import datetime
from pydantic import BaseModel, EmailStr
from typing import Generic, TypeVar

from src.enums import ErrorResponseCode

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