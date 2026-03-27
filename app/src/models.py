from datetime import datetime, date
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, DateTime, ForeignKey, func, Date, Enum, ARRAY
from src.enum import EducationType


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__: str = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String)
    password_hash: Mapped[str] = mapped_column(String)
    username: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class UserProfile(Base):
    __tablename__: str = "user_profiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    # full_name: Mapped[str] = mapped_column(String)
    nickname: Mapped[str] = mapped_column(String)
    birth: Mapped[date] = mapped_column(Date)
    education: Mapped[EducationType] = mapped_column(Enum(EducationType))
    school: Mapped[String] = mapped_column(String, nullable=True)
    department: Mapped[String] = mapped_column(String, nullable=True)
    phone: Mapped[str] = mapped_column(String(length=11), nullable=True)
    worry: Mapped[list[str]] = mapped_column(ARRAY(String))
    interest: Mapped[list[str]] = mapped_column(ARRAY(String))
    # profile_image_id: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class OauthAccount(Base):
    __tablename__: str = "oauth_accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    provider: Mapped[str] = mapped_column(String)
    provider_user_id: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


# class Plan(Base):
#     __tablename__: str = "plans"
#     id: Mapped[int] = mapped_column(primary_key=True)
#     name: Mapped[str] = mapped_column(String)
#     price: Mapped[int] = mapped_column(Integer)
#     billing_cycle: Mapped[str] = mapped_column(String)
#     features: Mapped[str] = mapped_column(String)


# class Subscription(Base):
#     __tablename__: str = "subscriptions"
#     id: Mapped[int] = mapped_column(primary_key=True)
#     user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
#     plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"), nullable=False)
#     status: Mapped[str] = mapped_column(String)
#     start_date: Mapped[datetime] = mapped_column(DateTime)
#     end_date: Mapped[datetime] = mapped_column(DateTime)
#     auto_renew: Mapped[bool] = mapped_column(Boolean)


# class Payment(Base):
#     __tablename__: str = "payments"
#     id: Mapped[int] = mapped_column(primary_key=True)
#     user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
#     subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id"), nullable=False)
#     amount: Mapped[int] = mapped_column(Integer)
#     currency: Mapped[str] = mapped_column(String)
#     payment_method: Mapped[str] = mapped_column(String)
#     status: Mapped[str] = mapped_column(String)
#     paid_at: Mapped[datetime] = mapped_column(DateTime)


# class Policy(Base):
#     __tablename__: str = "policies"
#     id: Mapped[int] = mapped_column(primary_key=True)
#     name: Mapped[str] = mapped_column(String)
#     type: Mapped[str] = mapped_column(String)
#     is_required: Mapped[bool] = mapped_column(Boolean)
#     created_at: Mapped[datetime] = mapped_column(DateTime)


# class PolicyVersion(Base):
#     __tablename__: str = "policy_versions"
#     id: Mapped[int] = mapped_column(primary_key=True)
#     policy_id: Mapped[int] = mapped_column(ForeignKey("policies.id"), nullable=False)
#     version: Mapped[str] = mapped_column(String)
#     content: Mapped[str] = mapped_column(String)
#     effective_date: Mapped[datetime] = mapped_column(DateTime)
#     created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# class UserPolicyAgreement(Base):
#     __tablename__: str = "user_policy_agreements"
#     id: Mapped[int] = mapped_column(primary_key=True)
#     user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
#     policy_version_id: Mapped[int] = mapped_column(ForeignKey("policy_versions.id"), nullable=False)
#     agreed_at: Mapped[datetime] = mapped_column(DateTime)
#     is_accepted: Mapped[bool] = mapped_column(Boolean)


# class Experience(Base):
#     __tablename__: str= "experiences"
#     id: Mapped[int] = mapped_column(primary_key=True)
#     user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
#     raw_text: Mapped[str] = mapped_column(String)
#     status: Mapped[str] = mapped_column(String)


# class Analysis(Base):
#     __tablename__: str= "analyses"
#     id: Mapped[int] = mapped_column(primary_key=True)
#     experience_id: Mapped[str] = mapped_column(String)
#     core_skill: Mapped[str] = mapped_column(String)
#     current_or_target_rule: Mapped[str] = mapped_column(String)
#     total_experience_years: Mapped[str] = mapped_column(String)
#     analysis_summary: Mapped[str] = mapped_column(String)
#     recommendations: Mapped[str] = mapped_column(String)