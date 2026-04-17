from datetime import datetime, date
from typing import Any
import uuid
from sqlalchemy import DateTime, func, Column, UUID as SAUUID
from sqlalchemy.sql.functions import now
from src.enums import AnalysisStatus, ExperiencePriority, OauthProviderId, UserStatus
from sqlmodel import ARRAY, Field, Relationship, SQLModel, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from pgvector.sqlalchemy import Vector

class User(SQLModel, table=True):
    __tablename__: str = "users"  # pyright: ignore[reportIncompatibleVariableOverride]
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_type=SAUUID
    )
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
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_type=SAUUID
    )
    user_id: uuid.UUID = Field(foreign_key="users.id", unique=True)
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
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_type=SAUUID
    )
    user_id: uuid.UUID = Field(foreign_key="users.id")
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
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_type=SAUUID
    )
    jti_hash: str = Field(unique=True, index=True)
    user_id: uuid.UUID = Field(foreign_key="users.id")
    iat: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    exp: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    next: uuid.UUID | None = None
    revoked: bool = False

class Experience(SQLModel, table=True):
    __tablename__: str = "experiences"  # pyright: ignore[reportIncompatibleVariableOverride]
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_type=SAUUID
    )
    user_id: uuid.UUID = Field(foreign_key="users.id")
    type: str
    priority: ExperiencePriority = ExperiencePriority.MEDIUM
    content: dict[str, Any] = Field(
        sa_column=Column(JSONB)
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

class Library(SQLModel, table=True):
    __tablename__: str = "libraries"  # pyright: ignore[reportIncompatibleVariableOverride]
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_type=SAUUID
    )
    user_id: uuid.UUID = Field(foreign_key="users.id")
    name: str = Field(nullable=False)
    color: str
    icon: str
    is_system: bool = False
    filter: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True)
    )
    sort_order: int = 0
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

class LibraryExperienceRelation(SQLModel, table=True):
    __tablename__: str = "libraries-experiences"  # pyright: ignore[reportIncompatibleVariableOverride]
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    library_id: uuid.UUID = Field(foreign_key="libraries.id", primary_key=True)
    experience_id: uuid.UUID = Field(foreign_key="experiences.id", primary_key=True)
    created_at: datetime = Field(
        default_factory=now,
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            nullable=False
        )
    )

class Preset(SQLModel, table=True):
    __tablename__: str = "presets"  # pyright: ignore[reportIncompatibleVariableOverride]
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_type=SAUUID
    )
    user_id: uuid.UUID = Field(foreign_key="users.id")
    name: str = Field(nullable=False)
    description: str | None
    blocks: list[dict[str, Any]] = Field(
        sa_column=Column(ARRAY(JSONB))
    )
    is_favorite: bool = False
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

class IndividualAnalysis(SQLModel, table=True):
    __tablename__: str = "individual_analyses"  # pyright: ignore[reportIncompatibleVariableOverride]
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_type=SAUUID
    )
    task_id: str | None = Field(nullable=True, index=True, default=None)
    status: AnalysisStatus = AnalysisStatus.QUEUED
    experience_id: uuid.UUID = Field(foreign_key="experiences.id")
    vector: list[float] | None = Field(
        default=None,
        sa_column=Column(Vector(3072), nullable=True, default=None)
    )
    result: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True, default=None)
    )

class ComprehensiveAnalysisExperienceLink(SQLModel, table=True):
    comprehensive_analysis_id: uuid.UUID = Field(foreign_key="comprehensive_analyses.id", primary_key=True)
    experience_id: uuid.UUID = Field(foreign_key="experiences.id", primary_key=True)

class ComprehensiveAnalysis(SQLModel, table=True):
    __tablename__: str = "comprehensive_analyses"  # pyright: ignore[reportIncompatibleVariableOverride]
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_type=SAUUID
    )
    task_id: str | None = Field(nullable=True, index=True, default=None)
    status: AnalysisStatus = AnalysisStatus.QUEUED
    experiences: list[Experience] = Relationship(
        back_populates="comprehensive_analyses",
        link_model=ComprehensiveAnalysisExperienceLink
    )
    vector: list[float] | None = Field(
        default=None,
        sa_column=Column(Vector(3072), nullable=True, default=None)
    )
    result: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True, default=None)
    )

class Resume(SQLModel, table=True):
    __tablename__: str = "resume"  # pyright: ignore[reportIncompatibleVariableOverride]
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_type=SAUUID
    )
    result: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True, default=None)
    )