from datetime import datetime, date
from sqlalchemy import DateTime, func, Column
from src.enums import EducationType
from sqlmodel import ARRAY, Field, SQLModel, String

class User(SQLModel, table=True):
    __tablename__: str = "users"
    id: int = Field(primary_key=True)
    email: str
    password_hash: str | None = None
    username: str
    status: str
    created_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            nullable=False
        )
    )
    updated_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            onupdate=func.now(),
            nullable=False
        )
    )

class UserProfile(SQLModel, table=True):
    __tablename__: str = "user_profiles"
    id: int = Field(primary_key=True)
    user_id: int = Field(foreign_key="users.id")
    nickname: str
    birth: date
    education: EducationType
    school: str | None = None
    department: str | None = None
    phone: str = Field(max_length=11)
    worry: list[str] = Field(
        sa_column=Column(ARRAY(String))
    )
    interest: list[str] = Field(
        sa_column=Column(ARRAY(String))
    )
    created_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            nullable=False
        )
    )
    updated_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            onupdate=func.now(),
            nullable=False
        )
    )

class OauthAccount(SQLModel, table=True):
    __tablename__: str = "oauth_accounts"
    id: int = Field(primary_key=True)
    user_id: int = Field(foreign_key="users.id")
    provider: str
    provider_user_id: str
    created_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            nullable=False
        )
    )
    updated_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            onupdate=func.now(),
            nullable=False
        )
    )