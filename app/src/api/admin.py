from fastapi import APIRouter, Depends, Request
from sqlalchemy import ARRAY, Enum
from sqlalchemy.sql.elements import Label
from sqlmodel import and_, col, select, func
from typing import Annotated, cast
from uuid import UUID

from src.api.models.base import AdminCustomerDetail, AdminCustomerDetailCustomer, AdminCustomerDetailProfile, ErrorResponse, SuccessResponseWithData
from src.api.models.exc import AppException
from src.db.db import SessionDep
from src.db.models import DeletedUser, OauthAccount, User, UserProfile
from src.enums import AuditAction, ErrorResponseCode, OauthProviderId
from src.utils.admin import log_audit, require_admin
from src.utils.token import AccessTokenPayload

admin_router = APIRouter()

@admin_router.get("/status")
async def admin_status():
    return {"status": "ok", "message": "Admin route is accessible."}

providers_col = cast(
    "Label[list[OauthProviderId]]",
    func.array_remove(
        func.array_agg(OauthAccount.provider),
        None,
        type_=ARRAY(Enum(OauthProviderId, name="oauthproviderid", create_type=False)),
    ).label("providers")
)

@admin_router.get("/customers/{customer_id}")
def get_customer(customer_id: UUID, session: SessionDep, payload: Annotated[AccessTokenPayload, Depends(require_admin)], request: Request):
    stmt = (
        select(
            User,
            UserProfile,
            DeletedUser.deleted_at,
            providers_col,
        )
        .select_from(User)
        .outerjoin(UserProfile, and_(UserProfile.user_id == User.id))
        .outerjoin(DeletedUser, and_(DeletedUser.user_id == User.id))
        .outerjoin(OauthAccount, and_(OauthAccount.user_id == User.id))
        .where(User.id == customer_id)
        .group_by(col(User.id), col(UserProfile.id), col(DeletedUser.user_id))
    )
    row = session.exec(stmt).one_or_none()
    if row is None:
        raise AppException(404, ErrorResponse(code=ErrorResponseCode.NOT_FOUND, message="not found"))

    user, profile, withdrawn_at, providers = row

    customer_detail = AdminCustomerDetail(
        customer = AdminCustomerDetailCustomer(
            id = user.id,
            email = user.email,
            name = profile.name if profile else None,
            status = user.status,
            onboarded = profile is not None,
            created_at = user.created_at,
            withdrawn_at = withdrawn_at,
            auth_providers = providers,
        ),
        profile = AdminCustomerDetailProfile(
            school = profile.school if profile else None,
            department = profile.department if profile else None,
            affiliation = profile.affiliation if profile else None,
            affiliation_detail = profile.affiliationDetail if profile else None,
            company = profile.company if profile else None,
            desired_role = profile.desiredRole if profile else None,
        ) if profile else None,
        # activity = AdminCustomerDetailActivity(
        #     experiences = get_activity_stat(session, Experience, customer_id, has_status=False),
        #     individual_analyses = get_activity_stat(session, IndividualAnalysis, customer_id, has_status=True),
        #     comprehensive_analyses = get_activity_stat(session, ComprehensiveAnalysis, customer_id, has_status=True),
        #     keyword_analyses = get_activity_stat(session, KeywordAnalysis, customer_id, has_status=True),
        #     resumes = get_activity_stat(session, Resume, customer_id, has_status=True),
        # )
    )

    log_audit(
        AuditAction.CUSTOMER_VIEW,
        payload,
        user.id,
        request
    )

    return SuccessResponseWithData(message="found", data=customer_detail)