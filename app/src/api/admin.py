from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import ARRAY, Enum
from sqlalchemy.sql.elements import Label
from sqlmodel import and_, col, or_, select, func
from typing import Annotated, cast
from uuid import UUID

from src.api.models.base import AdminActivityStat, AdminCustomerDetail, AdminCustomerDetailActivity, AdminCustomerDetailCustomer, AdminCustomerDetailProfile, AdminCustomerList, AdminCustomerListData, ErrorResponse, QueryParamsAuditLog, SuccessResponseWithData
from src.api.models.exc import AppException
from src.api.models.request import ListCustomersQueryParams
from src.db.db import SessionDep
from src.db.models import ComprehensiveAnalysis, CoverLetter, DeletedUser, Experience, IndividualAnalysis, KeywordAnalysis, OauthAccount, Resume, User, UserProfile
from src.enums import AnalysisStatus, AuditAction, ErrorResponseCode, OauthProviderId
from src.utils.admin import log_audit, require_admin
from src.utils.db import parse_sort
from src.utils.token import AccessTokenPayload

admin_router = APIRouter()

@admin_router.get("/status")
async def admin_status():
    return {"status": "ok", "message": "Admin route is accessible."}

def get_activity_stat_simple(
    session: SessionDep,
    model: type[Experience],
    customer_id: UUID,
):
    stmt = (
        select(func.count(), func.max(model.created_at))
        .where(model.user_id == customer_id)
    )
    total, last_at = session.exec(stmt).one()
    return AdminActivityStat(total=total, last_at=last_at, by_status=None)

def get_activity_stat_by_status(
    session: SessionDep,
    model: type[IndividualAnalysis] | type[ComprehensiveAnalysis] | type[KeywordAnalysis] | type[Resume] | type[CoverLetter],
    customer_id: UUID,
):
    stmt = (
        select(model.status, func.count(), func.max(model.created_at))
        .where(model.user_id == customer_id)
        .group_by(col(model.status))
    )
    rows = session.exec(stmt).all()

    by_status = {status: 0 for status in AnalysisStatus}
    last_at = None
    for status, count, latest in rows:
        if not isinstance(status, AnalysisStatus):
            raise AppException(500, ErrorResponse(code=ErrorResponseCode.SERVER_ERROR, message="Invalid status value"))
        by_status[status] = count
        if latest is not None and (last_at is None or latest > last_at):
            last_at = latest

    return AdminActivityStat(
        total=sum(by_status.values()),
        last_at=last_at,
        by_status=by_status,
    )

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
        raise AppException(404, ErrorResponse(code=ErrorResponseCode.NOT_FOUND, message="Customer not found"))

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
        activity = AdminCustomerDetailActivity(
            experiences = get_activity_stat_simple(session, Experience, customer_id),
            individual_analyses = get_activity_stat_by_status(session, IndividualAnalysis, customer_id),
            comprehensive_analyses = get_activity_stat_by_status(session, ComprehensiveAnalysis, customer_id),
            keyword_analyses = get_activity_stat_by_status(session, KeywordAnalysis, customer_id),
            resumes = get_activity_stat_by_status(session, Resume, customer_id),
            cover_letters = get_activity_stat_by_status(session, CoverLetter, customer_id)
        )
    )

    log_audit(
        AuditAction.CUSTOMER_VIEW,
        payload,
        user.id,
        request,
        None
    )

    return SuccessResponseWithData(message="found", data=customer_detail)

@admin_router.get("/customers")
def list_customers(query: Annotated[ListCustomersQueryParams, Query()], session: SessionDep, payload: Annotated[AccessTokenPayload, Depends(require_admin)], request: Request):
    sort_field_name, sort_is_descending = parse_sort(query.sort, ["created_at"])
    sort_column = getattr(User, sort_field_name)
    order_clause = sort_column.desc() if sort_is_descending else sort_column.asc()
    base_stmt = (
        select(
            User,
            UserProfile,
            DeletedUser.deleted_at,
        )
        .select_from(User)
        .outerjoin(UserProfile, and_(UserProfile.user_id == User.id))
        .outerjoin(DeletedUser, and_(DeletedUser.user_id == User.id))
        .group_by(col(User.id), col(UserProfile.id), col(DeletedUser.user_id))
    )
    if query.q:
        base_stmt = base_stmt.where(
            or_(col(User.email).ilike(f"%{query.q}%"), col(UserProfile.name).ilike(f"%{query.q}%"))
        )
    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    count = session.exec(count_stmt).one()
    page_stmt = base_stmt.order_by(order_clause).offset(query.offset).limit(query.limit)
    rows = session.exec(page_stmt).all()

    customers: list[AdminCustomerListData] = []
    for user, profile, withdrawn_at in rows:
        customers.append(AdminCustomerListData(
            id = user.id,
            email = user.email,
            name = profile.name if profile else None,
            status = user.status,
            onboarded = profile is not None,
            created_at = user.created_at,
            withdrawn_at = withdrawn_at,
        ))

    query_params = QueryParamsAuditLog(
        q = query.q,
        limit = query.limit,
        offset = query.offset,
        sort = query.sort,
        result_user_ids = [str(user.id) for user, _, _ in rows]
    )

    log_audit(
        AuditAction.CUSTOMER_LIST,
        payload,
        None,
        request,
        query_params
    )

    return SuccessResponseWithData(
        message = "found",
        data = AdminCustomerList(
            count = count,
            contents = customers
        )
    )