from datetime import datetime, date
from typing import Any
import uuid
from sqlalchemy import DateTime, func, Column, UUID as SAUUID
from sqlalchemy.sql.functions import now
from src.enums import OauthProviderId, UserStatus
from sqlmodel import ARRAY, Field, SQLModel, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from pgvector.sqlalchemy import Vector

class User(SQLModel, table=True):
    __tablename__: str = "users"  # pyright: ignore[reportIncompatibleVariableOverride]
    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(unique=True)
    password_hash: str | None = None
    status: UserStatus = Field(default=UserStatus.UNVERIFIED)
    created_at: datetime = Field(
        default_factory=now,
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            nullable=False
        )
    )
    updated_at: datetime = Field(
        default_factory=now,
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            onupdate=func.now(),
            nullable=False
        )
    )

class UserProfile(SQLModel, table=True):
    __tablename__: str = "user_profiles"  # pyright: ignore[reportIncompatibleVariableOverride]
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", unique=True)
    name: str
    birth: date
    phone: str = Field(max_length=11)
    education: str
    school: str | None = None
    department: str | None = None
    worry: list[str] = Field(
        sa_column=Column(ARRAY(String))
    )
    interest: list[str] = Field(
        sa_column=Column(ARRAY(String))
    )
    created_at: datetime = Field(
        default_factory=now,
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            nullable=False
        )
    )
    updated_at: datetime = Field(
        default_factory=now,
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            onupdate=func.now(),
            nullable=False
        )
    )

class OauthAccount(SQLModel, table=True):
    __tablename__: str = "oauth_accounts"  # pyright: ignore[reportIncompatibleVariableOverride]
    __table_args__: tuple[UniqueConstraint] = (
        UniqueConstraint("provider", "provider_user_id"),
    )
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id")
    provider: OauthProviderId
    provider_user_id: str
    created_at: datetime = Field(
        default_factory=now,
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            nullable=False
        )
    )
    updated_at: datetime = Field(
        default_factory=now,
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            onupdate=func.now(),
            nullable=False
        )
    )

class Token(SQLModel, table=True):
    __tablename__: str = "tokens"  # pyright: ignore[reportIncompatibleVariableOverride]
    id: int | None = Field(default=None, primary_key=True)
    jti_hash: str = Field(unique=True, index=True)
    user_id: int = Field(foreign_key="users.id")
    iat: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    exp: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    next: int | None = None
    revoked: bool = False

class IndividualAnalysis(SQLModel, table=True):
    __tablename__: str = "individual_analyses"  # pyright: ignore[reportIncompatibleVariableOverride]
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_type=SAUUID
    )
    vector: list[float] = Field(sa_column=Column(Vector(3072)))
    result: dict[str, Any] = Field(
        sa_column=Column(JSONB)
    )

class ComprehensiveAnalysis(SQLModel, table=True):
    __tablename__: str = "individual_analyses"  # pyright: ignore[reportIncompatibleVariableOverride]
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_type=SAUUID
    )
    vector: list[float] = Field(sa_column=Column(Vector(3072)))
    result: dict[str, Any] = Field(
        sa_column=Column(JSONB)
    )

class Resume(SQLModel, table=True):
    __tablename__: str = "resume"  # pyright: ignore[reportIncompatibleVariableOverride]
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_type=SAUUID
    )
    result: dict[str, Any] = Field(
        sa_column=Column(JSONB)
    )