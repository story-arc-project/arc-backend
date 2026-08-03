from datetime import datetime, date
from typing import Any, Optional
import uuid
from sqlalchemy import CheckConstraint, DateTime, func, Column, UUID as SAUUID
from sqlalchemy.sql.functions import now
from src.enums import Affiliation, AnalysisStatus, AnalysisType, AuditAction, FeedbackTriggerSource, Language, OauthProviderId, UserStatus
from sqlmodel import ARRAY, Field, SQLModel, String, UniqueConstraint
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
            index=True,
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
    affiliation: Affiliation
    school: str | None = None
    department: str | None = None
    company: str | None = None
    desiredRole: str | None = None
    affiliationDetail: str | None = None
    phone: str = Field(max_length=11)
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
    importance: int | None
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
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
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

class ComprehensiveAnalysis(SQLModel, table=True):
    __tablename__: str = "comprehensive_analyses"  # pyright: ignore[reportIncompatibleVariableOverride]
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_type=SAUUID
    )
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    task_id: str | None = Field(nullable=True, index=True, default=None)
    status: AnalysisStatus = AnalysisStatus.QUEUED
    title: str
    experience_ids: list[uuid.UUID] = Field(
        sa_column=Column(ARRAY(SAUUID))
    )
    vector: list[float] | None = Field(
        default=None,
        sa_column=Column(Vector(3072), nullable=True, default=None)
    )
    result: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True, default=None)
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

class Resume(SQLModel, table=True):
    __tablename__: str = "resume"  # pyright: ignore[reportIncompatibleVariableOverride]
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_type=SAUUID
    )
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    language: Language
    title: str
    status: AnalysisStatus = AnalysisStatus.QUEUED
    result: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True, default=None)
    )
    experience_ids: list[uuid.UUID] | None = Field(
        default=None,
        sa_column=Column(ARRAY(SAUUID), nullable=True, default=None)
    )
    task_id: str | None = Field(nullable=True, index=True, default=None)
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

class KeywordAnalysis(SQLModel, table=True):
    __tablename__: str = "keyword_analyses"  # pyright: ignore[reportIncompatibleVariableOverride]
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_type=SAUUID
    )
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    keywords: list[str] = Field(sa_column=Column(ARRAY(String)))
    task_id: str | None = Field(nullable=True, index=True, default=None)
    status: AnalysisStatus = AnalysisStatus.QUEUED
    target: str
    title: str
    result: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True, default=None)
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

class DeletedUser(SQLModel, table=True):
    __tablename__: str = "deleted_users"  # pyright: ignore[reportIncompatibleVariableOverride]
    user_id: uuid.UUID = Field(foreign_key="users.id", primary_key=True, sa_type=SAUUID)
    deleted_at: datetime = Field(
        default_factory=now,
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            nullable=False
        )
    )

class TermsConsent(SQLModel, table=True):
    __tablename__: str = "terms_consent"  # pyright: ignore[reportIncompatibleVariableOverride]
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_type=SAUUID
    )
    user_id: uuid.UUID = Field(foreign_key="users.id", sa_type=SAUUID)
    consent_id: str
    version: str | None = Field(nullable=True, default=None)
    granted: bool
    ip: str | None = Field(nullable=True, default=None)
    agreed_at: datetime = Field(
        default_factory=now,
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            onupdate=func.now(),
            nullable=False
        )
    )

class FileMetadata(SQLModel, table=True):
    __tablename__: str = "file_metadata"  # pyright: ignore[reportIncompatibleVariableOverride]
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_type=SAUUID
    )
    user_id: uuid.UUID = Field(foreign_key="users.id", sa_type=SAUUID)
    key: str = Field(unique=True, index=True)
    filename: str
    content_type: str
    size: int
    confirmed: bool = False
    created_at: datetime = Field(
        default_factory=now,
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            nullable=False
        )
    )

class AnalysisBookmark(SQLModel, table=True):
    __tablename__: str = "analysis_bookmarks"  # pyright: ignore[reportIncompatibleVariableOverride]
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "analysis_type",
            "analysis_id",
            name="uq_analysis_bookmark_user_type_analysis",
        ),
    )
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_type=SAUUID
    )
    user_id: uuid.UUID = Field(foreign_key="users.id", sa_type=SAUUID)
    analysis_type: AnalysisType = Field(nullable=False)
    analysis_id: uuid.UUID = Field(nullable=False, index=True)
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

class CoverLetter(SQLModel, table=True):
    __tablename__: str = "cover_letters"  # pyright: ignore[reportIncompatibleVariableOverride]
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_type=SAUUID
    )
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    task_id: str | None = Field(nullable=True, index=True, default=None)
    status: AnalysisStatus = AnalysisStatus.QUEUED
    target_company: str | None = None
    target_job: str | None = None
    job_key: str = "general"
    region: str = "KR"
    questions: list[dict[str, Any]] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True, default=None)
    )
    experience_ids: list[uuid.UUID] | None = Field(
        default=None,
        sa_column=Column(ARRAY(SAUUID), nullable=True, default=None)
    )
    result: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True, default=None)
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

class AuditLog(SQLModel, table=True):
    __tablename__: str = "audit_logs"  # pyright: ignore[reportIncompatibleVariableOverride]
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_type=SAUUID
    )
    actor_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    action: AuditAction = Field(index=True)
    target_user_id: Optional[uuid.UUID] = Field(foreign_key="users.id", index=True, default=None)
    query_params: Optional[dict] = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True)
    )
    timestamp: datetime = Field(
        default_factory=now,
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            nullable=False
        )
    )
    ip_address: Optional[str] = Field(default=None, max_length=45)
    user_agent: Optional[str] = Field(default=None, max_length=512)

class FeedbackResponse(SQLModel, table=True):
    __tablename__: str = "feedback_responses"  # pyright: ignore[reportIncompatibleVariableOverride]
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_type=SAUUID
    )
    user_id: uuid.UUID = Field(foreign_key="users.id", sa_type=SAUUID, index=True)
    campaign_id: str
    trigger_source: Optional[FeedbackTriggerSource] = Field(default=None, nullable=True)
    rating: Optional[int] = Field(default=None, nullable=True)
    comment: Optional[str] = Field(default=None, max_length=500, nullable=True)
    responded_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=True
        )
    )
    context: Optional[dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True)
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

    __table_args__ = (
        UniqueConstraint("user_id", "campaign_id", name="uq_feedback_user_campaign"),
        CheckConstraint("rating BETWEEN 1 AND 5", name="ck_feedback_rating_range"),
    )