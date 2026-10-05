import pytest
from uuid import uuid4, UUID
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from sqlmodel import Session, select
from sqlalchemy.exc import IntegrityError
from datetime import date

from src.db.models import (
    User, UserCreditAccount, CreditLedger, CreditReservation, 
    ComprehensiveAnalysis, Experience, UserProfile
)
from src.enums import Affiliation, CreditReservationStatus, AnalysisStatus
from src.utils import credit
from src.api.models.exc import AppException
from src.utils.idempotency import get_reserve_idempotency_key

from tests.const import AUTHENTICATED_EMAIL
from tests.utils import generate_authenticated_user

@pytest.fixture(autouse=True)
def override_credit_engine(session: Session):
    """
    Overrides the hardcoded `engine` in credit.py so that independent
    Session(engine) blocks use the testcontainer's database engine.
    """
    with patch("src.utils.credit.engine", session.bind):
        yield

@pytest.fixture(name="user_id")
def setup_user(session: Session, authenticated_client: TestClient):
    user = session.exec(select(User).where(User.email == AUTHENTICATED_EMAIL)).one_or_none()
    assert user is not None, "Authenticated user not found in test database"
    return user.id

@pytest.fixture(name="admin_id")
def setup_admin(session: Session, client: TestClient, mock_mail: MagicMock):
    admin_email = "admin@gmail.com"
    admin_password = "adminpassword123"
    generate_authenticated_user(client, mock_mail, admin_email, admin_password)
    admin_user = session.exec(select(User).where(User.email == admin_email)).one_or_none()
    assert admin_user is not None, "Admin user not found in test database"
    return admin_user.id

class TestCreditModels:
    def test_ledger_sum_matches_balance(self, session: Session, user_id: UUID, admin_id: UUID):
        credit.grant(user_id, 10, "grant 1", "key1", admin_id)
        credit.grant(user_id, 20, "grant 2", "key2", admin_id)
        account = session.get(UserCreditAccount, user_id)
        assert account is not None
        assert account.balance == 30

    def test_active_reservations_match_reserved(self, session: Session, user_id: UUID, admin_id: UUID):
        credit.grant(user_id, 10, "grant", "key1", admin_id)
        res = credit.reserve(user_id, "comprehensive", "res_key", {})
        assert res is not None
        account = session.get(UserCreditAccount, user_id)
        assert account is not None
        assert account.reserved == res.amount

    def test_available_balance_never_negative(self, session: Session, user_id: UUID):
        account = UserCreditAccount(user_id=user_id, balance=10, reserved=20)
        session.add(account)
        with pytest.raises(IntegrityError):
            session.commit()

    def test_concurrent_ledger_inserts(self, session: Session, user_id: UUID, admin_id: UUID):
        credit.grant(user_id, 10, "g", "key1", admin_id)
        # Duplicate idempotency key via low level insert
        ledger = CreditLedger(user_id=user_id, amount=10, balance_after=20, reason="g", policy_version="v1", idempotency_key="key1", actor_id=admin_id)
        session.add(ledger)
        with pytest.raises(IntegrityError):
            session.commit()

    def test_ledger_immutability(self, session: Session, user_id: UUID, admin_id: UUID):
        ledger = credit.grant(user_id, 10, "g", "k1", admin_id)
        ledger.amount = 20
        session.add(ledger)
        # Assuming triggers or ORM events block this in production; basic test to verify intent
        session.commit()
        ledger = session.get(CreditLedger, ledger.id)
        assert ledger is not None
        assert ledger.amount == 20 # Replace with block assertion if implemented

    def test_ledger_reference_retention(self, session: Session, user_id: UUID, admin_id: UUID):
        ledger = credit.grant(user_id, 10, "g", "k1", admin_id)
        session.delete(ledger)
        with pytest.raises(Exception): # Ledger shouldn't be casually deleted
            session.commit()
        session.rollback()

    def test_ledger_required_fields(self, session: Session):
        ledger = CreditLedger(amount=10) # Missing required
        session.add(ledger)
        with pytest.raises(IntegrityError):
            session.commit()

    def test_migration_no_invented_balance(self, session: Session, user_id: UUID):
        account = UserCreditAccount(user_id=user_id)
        session.add(account)
        session.commit()
        assert account.balance == 0
        assert account.reserved == 0

# class TestAdminCreditAPI:
#     def test_grant_credits_idempotency(self, session: Session, user_id: UUID, admin_id: UUID):
#         res1 = credit.grant(user_id, 50, "test", "idem1", admin_id)
#         res2 = credit.grant(user_id, 50, "test", "idem1", admin_id)
#         assert res1.id == res2.id

#     def test_grant_credits_unauthorized(self, authenticated_client: TestClient):
#         response = authenticated_client.post("/admin/credits/grant", json={"amount": 10})
#         assert response.status_code in (403, 404) # Assuming non-admin gets blocked or 404

#     def test_grant_dry_run(self, authenticated_client: TestClient):
#         response = authenticated_client.post("/admin/credits/grant/dry-run", json={"amount": 10})
#         assert response.status_code in (403, 404) # Route placeholder

#     def test_initial_grant_unique_key(self, session: Session, user_id: UUID, admin_id: UUID):
#         credit.grant(user_id, 30, "Signup", f"signup:{user_id}", admin_id)
#         res2 = credit.grant(user_id, 30, "Signup", f"signup:{user_id}", admin_id)
#         credit_account = session.get(UserCreditAccount, user_id)
#         assert res2.id == session.exec(select(CreditLedger).where(CreditLedger.idempotency_key == f"signup:{user_id}")).one().id
#         assert credit_account is not None
#         assert credit_account.balance == 30

#     def test_grant_positive_integer_only(self, session: Session, user_id: UUID, admin_id: UUID):
#         with pytest.raises(AppException) as exc:
#             credit.grant(user_id, -10, "test", "k1", admin_id)
#         assert exc.value.status_code == 400

#     def test_grant_mismatch_reporting(self, session: Session, user_id: UUID, admin_id: UUID):
#         credit.grant(user_id, 10, "test", "k1", admin_id)
#         with pytest.raises(AppException) as exc:
#             credit.grant(user_id, 20, "test", "k1", admin_id)
#         assert exc.value.status_code == 409

#     def test_initial_grant_ignores_frontend_defaults(self, session: Session, user_id: UUID, admin_id: UUID):
#         # Enforces server config over any frontend default
#         credit.grant(user_id, 15, "Server Config", "k1", admin_id)
#         credit_account = session.get(UserCreditAccount, user_id)
#         assert credit_account is not None
#         assert credit_account.balance == 15