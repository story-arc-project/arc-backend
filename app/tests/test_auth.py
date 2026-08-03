from datetime import datetime, timedelta, timezone
from time import sleep
from uuid import uuid4
import pytest  
from fastapi.testclient import TestClient
from sqlmodel import Session, select
from unittest.mock import MagicMock, patch
from email.mime.multipart import MIMEMultipart
from freezegun import freeze_time

from src.utils.token import hash_jti, verify_refresh_token
from src.const import REFRESH_TOKEN_EXPIRE, VERIFICATION_MAX_ATTEMPTS, LOGIN_MAX_RETRY_COUNT, LOGIN_RETRY_COOLDOWN
from src.db.models import Token
from src.utils.mail import send_mail
from src.enums import ErrorResponseCode, JWTTokenStatus
from src.db.red import is_locked, increment_attempt, set_lockout, clear, get_attempt_count
from src.api.models.consent import AGREEABLE_CONSENT_VERSIONS
from tests.const import AUTHENTICATED_EMAIL


# Test data
email = AUTHENTICATED_EMAIL
password = "testpassword123"


def get_sent_mail(mock_mail: MagicMock):
    sent_mail: MIMEMultipart = mock_mail.send_message.call_args.args[0]
    for part in sent_mail.walk():
        if part.is_multipart():
            continue

        if part.get_content_type() in ("text/plain", "text/html"):
            return {
                "To": sent_mail["To"],
                "Subject": sent_mail["Subject"],
                "Content-Type": part.get_content_type(),
                "Body": part.get_payload(decode=True).decode(
                    part.get_content_charset() or "utf-8"
                )
            }
    return {
        "To": sent_mail["To"],
        "Subject": sent_mail["Subject"],
        "Content-Type": None,
        "Body": None
    }


def test_send_mail(mock_mail: MagicMock):
    to = "senttest@gmail.com"
    subject = "hi"
    body = "hi"

    _ = send_mail(to, subject, body)
    mock_mail.send_message.assert_called_once()

    sent_mail = get_sent_mail(mock_mail)
    assert sent_mail["To"] == to
    assert sent_mail["Subject"] == subject
    assert sent_mail["Body"] == body


def test_signup(client: TestClient, mock_mail: MagicMock):
    response = client.post(
        "/auth/signup",
        json={
            "email": email,
            "password": "weak"
        }
    )
    assert response.status_code == 400
    assert response.json()["code"] == "WEAK_PASSWORD"
    
    response = client.post(
        "/auth/signup",
        json={
            "email": email,
            "password": password
        }
    )

    assert response.status_code == 201

    response = client.post(
        "/auth/signup",
        json={
            "email": email,
            "password": password + "2"
        }
    )

    assert response.status_code == 409
    assert get_sent_mail(mock_mail)["To"] == email


def _do_verification_flow(client: TestClient, mock_mail: MagicMock, expect_remaining_attempts: bool):
    response = client.post(
        "/auth/signup",
        json={
            "email": email,
            "password": password
        }
    )

    exp = 0.02
    with patch("src.db.red.VERIFICATION_CODE_EXPIRE", exp):
        response = client.post(
            "/auth/resend-verification",
            json={
                "email": email
            }
        )

        assert response.status_code == 200

        sent_mail = get_sent_mail(mock_mail)
        assert sent_mail["To"] == email

        code = sent_mail["Body"] # TODO: Assume body has only code

        sleep(int(exp * 60) + 1)
    
        response = client.post(
            "/auth/verify-email",
            json={
                "email": email,
                "code": code
            }
        )

        assert response.status_code == 400
        assert response.cookies.get("accessToken") is None
        assert response.cookies.get("refreshToken") is None
    
    response = client.post(
        "/auth/resend-verification",
        json={
            "email": email
        }
    )

    assert response.status_code == 200

    sent_mail = get_sent_mail(mock_mail)
    assert sent_mail["To"] == email

    code = sent_mail["Body"]

    # Test that remaining_attempts decrements with each wrong attempt
    prev_remaining = None
    for _ in range(VERIFICATION_MAX_ATTEMPTS - 1):
        response = client.post(
            "/auth/verify-email",
            json={
                "email": email,
                "code": "1234"
            }
        )

        assert response.status_code == 400
        assert response.cookies.get("accessToken") is None
        assert response.cookies.get("refreshToken") is None

        data = response.json()
        if expect_remaining_attempts:
            assert "remaining_attempts" in data
            remaining = data["remaining_attempts"]
            assert remaining >= 0
            if prev_remaining is not None:
                assert remaining == prev_remaining - 1
            prev_remaining = remaining
        else:
            assert "remaining_attempts" not in data

    # Final wrong attempt exhausts the code; remaining_attempts is 0, not negative
    response = client.post(
        "/auth/verify-email",
        json={
            "email": email,
            "code": "1234"
        }
    )

    assert response.status_code == 429
    assert response.cookies.get("accessToken") is None
    assert response.cookies.get("refreshToken") is None
    data = response.json()

    # Correct code also fails now since attempts are exhausted
    response = client.post(
        "/auth/verify-email",
        json={
            "email": email,
            "code": code
        }
    )

    assert response.status_code == 429
    assert response.cookies.get("accessToken") is None
    assert response.cookies.get("refreshToken") is None
    data = response.json()

    # Resend and verify successfully
    response = client.post(
        "/auth/resend-verification",
        json={
            "email": email
        }
    )

    assert response.status_code == 200

    sent_mail = get_sent_mail(mock_mail)
    assert sent_mail["To"] == email

    code = sent_mail["Body"]

    response = client.post(
        "/auth/verify-email",
        json={
            "email": email,
            "code": code
        }
    )

    assert response.status_code == 200
    assert response.cookies.get("accessToken") is not None
    assert response.cookies.get("refreshToken") is not None

    response = client.post(
        "/auth/resend-verification",
        json={
            "email": email
        }
    )

    assert response.status_code == 400

def _do_verification_flow_wrapper(client: TestClient, mock_mail: MagicMock, expect_remaining_attempts: bool):
    with patch("src.api.auth.VERIFY_EMAIL_MAX_RETRY_COUNT", 1000):
        with patch("src.api.auth.SHOW_REMAINING_VERIFICATION_ATTEMPTS", expect_remaining_attempts):
            _do_verification_flow(client, mock_mail, expect_remaining_attempts)

def test_verification_with_remaining_attempts(client: TestClient, mock_mail: MagicMock):
    _do_verification_flow_wrapper(client, mock_mail, True)

def test_verification_without_remaining_attempts(client: TestClient, mock_mail: MagicMock):
    _do_verification_flow_wrapper(client, mock_mail, False)


def test_login(client: TestClient, mock_mail: MagicMock):
    response = client.post(
        "/auth/signup",
        json={
            "email": email,
            "password": password
        }
    )

    response = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": password
        }
    )

    assert response.status_code == 403
    assert response.cookies.get("accessToken") is None
    assert response.cookies.get("refreshToken") is None

    code = get_sent_mail(mock_mail)["Body"]

    response = client.post(
        "/auth/verify-email",
        json={
            "email": email,
            "code": code
        }
    )

    assert response.status_code == 200

    response = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": password
        }
    )

    assert response.status_code == 200
    assert response.cookies.get("accessToken") is not None
    assert response.cookies.get("refreshToken") is not None

class TestLockdown:

    # --- is_locked ---

    def test_not_locked_by_default(self):
        locked, ttl = is_locked("login:email:test@test.com")
        assert locked is False
        assert ttl == 0

    def test_locked_after_set_lockout(self):
        set_lockout("login:email:test@test.com", LOGIN_RETRY_COOLDOWN)
        locked, ttl = is_locked("login:email:test@test.com")
        assert locked is True
        assert 0 < ttl <= LOGIN_RETRY_COOLDOWN * 60

    # --- increment_attempt ---

    def test_first_attempt_returns_one(self):
        count = increment_attempt("login:email:test@test.com", LOGIN_RETRY_COOLDOWN)
        assert count == 1

    def test_attempt_increments_correctly(self):
        for expected in range(1, LOGIN_MAX_RETRY_COUNT):
            count = increment_attempt("login:email:test@test.com", LOGIN_RETRY_COOLDOWN)
            assert count == expected

    def test_attempt_counter_has_ttl_after_first(self):
        increment_attempt("login:email:test@test.com", LOGIN_RETRY_COOLDOWN)
        assert get_attempt_count("login:email:test@test.com") == 1

    # --- set_lockout ---

    def test_lockout_clears_attempt_counter(self):
        for _ in range(LOGIN_MAX_RETRY_COUNT):
            increment_attempt("login:email:test@test.com", LOGIN_RETRY_COOLDOWN)

        set_lockout("login:email:test@test.com", LOGIN_RETRY_COOLDOWN)
        assert get_attempt_count("login:email:test@test.com") == 0

    def test_lockout_sets_cooldown(self):
        set_lockout("login:email:test@test.com", LOGIN_RETRY_COOLDOWN)
        locked, _ = is_locked("login:email:test@test.com")
        assert locked is True

    # --- clear ---

    def test_clear_resets_attempt_counter(self):
        for _ in range(3):
            increment_attempt("login:email:test@test.com", LOGIN_RETRY_COOLDOWN)

        clear("login:email:test@test.com")
        assert get_attempt_count("login:email:test@test.com") == 0

    def test_clear_removes_lockout(self):
        set_lockout("login:email:test@test.com", LOGIN_RETRY_COOLDOWN)
        clear("login:email:test@test.com")
        locked, _ = is_locked("login:email:test@test.com")
        assert locked is False

    # --- integration: full lockout flow ---

    def test_lockout_triggers_at_max_attempts(self):
        key = "login:email:test@test.com"

        for _ in range(LOGIN_MAX_RETRY_COUNT):
            count = increment_attempt(key, LOGIN_RETRY_COOLDOWN)

        set_lockout(key, LOGIN_RETRY_COOLDOWN)

        locked, ttl = is_locked(key)
        assert locked is True
        assert ttl > 0
        assert get_attempt_count(key) == 0

    def test_fresh_attempts_after_clear(self):
        key = "login:email:test@test.com"

        for _ in range(LOGIN_MAX_RETRY_COUNT):
            increment_attempt(key, LOGIN_RETRY_COOLDOWN)
        set_lockout(key, LOGIN_RETRY_COOLDOWN)
        clear(key)

        locked, _ = is_locked(key)
        assert locked is False
        assert get_attempt_count(key) == 0

    def test_ip_and_email_are_independent(self):
        """Lockout on IP should not affect email key and vice versa."""
        for _ in range(LOGIN_MAX_RETRY_COUNT):
            increment_attempt("login:ip:192.168.0.1", LOGIN_RETRY_COOLDOWN)
        set_lockout("login:ip:192.168.0.1", LOGIN_RETRY_COOLDOWN)

        locked, _ = is_locked("login:email:test@test.com")
        assert locked is False

    def test_different_users_are_isolated(self):
        """Failures for one user should not affect another."""
        for _ in range(LOGIN_MAX_RETRY_COUNT):
            increment_attempt("login:email:attacker@evil.com", LOGIN_RETRY_COOLDOWN)
        set_lockout("login:email:attacker@evil.com", LOGIN_RETRY_COOLDOWN)

        locked, _ = is_locked("login:email:innocent@test.com")
        assert locked is False

    def test_login_wrong_password_increments_attempts(self, client: TestClient, mock_mail: MagicMock, fake_redis):
        # signup and verify first
        client.post("/auth/signup", json={"email": email, "password": password})
        code = get_sent_mail(mock_mail)["Body"]
        client.post("/auth/verify-email", json={"email": email, "code": code})

        response = client.post("/auth/login", json={"email": email, "password": "wrongpassword"})

        assert response.status_code == 401
        assert get_attempt_count(f"login:email:{email}") == 1

    def test_login_lockout_after_max_attempts(self, client: TestClient, mock_mail: MagicMock, fake_redis):
        client.post("/auth/signup", json={"email": email, "password": password})
        code = get_sent_mail(mock_mail)["Body"]
        client.post("/auth/verify-email", json={"email": email, "code": code})

        for _ in range(LOGIN_MAX_RETRY_COUNT - 1):
            response = client.post("/auth/login", json={"email": email, "password": "wrongpassword"})
            assert response.status_code == 401

        # final attempt triggers lockout
        response = client.post("/auth/login", json={"email": email, "password": "wrongpassword"})
        assert response.status_code == 429

        locked, ttl = is_locked(f"login:email:{email}")
        assert locked is True
        assert ttl > 0

    def test_login_blocked_when_locked(self, client: TestClient, mock_mail: MagicMock, fake_redis):
        client.post("/auth/signup", json={"email": email, "password": password})
        code = get_sent_mail(mock_mail)["Body"]
        client.post("/auth/verify-email", json={"email": email, "code": code})

        # force lockout
        set_lockout(f"login:email:{email}", LOGIN_RETRY_COOLDOWN)

        # even correct password is rejected
        response = client.post("/auth/login", json={"email": email, "password": password})
        assert response.status_code == 429

    def test_login_clears_attempts_on_success(self, client: TestClient, mock_mail: MagicMock, fake_redis):
        client.post("/auth/signup", json={"email": email, "password": password})
        code = get_sent_mail(mock_mail)["Body"]
        client.post("/auth/verify-email", json={"email": email, "code": code})

        # fail a couple times
        for _ in range(2):
            client.post("/auth/login", json={"email": email, "password": "wrongpassword"})
        assert get_attempt_count(f"login:email:{email}") == 2

        # succeed
        response = client.post("/auth/login", json={"email": email, "password": password})
        assert response.status_code == 200  # unverified would be 403, here it's verified so 200
        assert get_attempt_count(f"login:email:{email}") == 0
        locked, _ = is_locked(f"login:email:{email}")
        assert locked is False

    def test_login_ip_lockout_blocks_request(self, client: TestClient, mock_mail: MagicMock, fake_redis):
        client.post("/auth/signup", json={"email": email, "password": password})
        code = get_sent_mail(mock_mail)["Body"]
        client.post("/auth/verify-email", json={"email": email, "code": code})

        # simulate IP lockout directly
        ip = "testclient"  # default IP from Starlette TestClient
        set_lockout(f"login:ip:{ip}", LOGIN_RETRY_COOLDOWN)

        response = client.post("/auth/login", json={"email": email, "password": password})
        assert response.status_code == 429

    def test_login_nonexistent_email_still_increments(self, client: TestClient, fake_redis):
        response = client.post("/auth/login", json={"email": "ghost@test.com", "password": "whatever"})
        assert response.status_code == 401
        assert get_attempt_count("login:email:ghost@test.com") == 1
    
    def test_login_allowed_after_cooldown(self, client: TestClient, mock_mail: MagicMock, fake_redis):
        client.post("/auth/signup", json={"email": email, "password": password})
        code = get_sent_mail(mock_mail)["Body"]
        client.post("/auth/verify-email", json={"email": email, "code": code})

        for _ in range(LOGIN_MAX_RETRY_COUNT):
            client.post("/auth/login", json={"email": email, "password": "wrongpassword"})

        locked, _ = is_locked(f"login:email:{email}")
        assert locked is True

        # manually expire the cooldown key to simulate time passing
        fake_redis.delete(f"cooldown:login:email:{email}")

        response = client.post("/auth/login", json={"email": email, "password": password})
        assert response.status_code == 200
        assert response.cookies.get("accessToken") is not None


def test_refresh(session: Session, client: TestClient, mock_mail: MagicMock):
    # 1. Missing cookie
    response = client.post("/auth/refresh")
    assert response.status_code == 401
    assert response.json()["code"] == ErrorResponseCode.AUTH_MISSING_COOKIES

    # 2. Invalid token
    client.cookies.set("refreshToken", "bad")
    response = client.post("/auth/refresh")
    assert response.status_code == 401
    assert response.json()["code"] == ErrorResponseCode.AUTH_TOKEN_INVALID

    # 3. Expired token (JWT-level)
    client.cookies.clear()
    response = client.post(
        "/auth/signup",
        json={
            "email": email,
            "password": password
        }
    )
    past_time = datetime.now(timezone.utc) - timedelta(days=(REFRESH_TOKEN_EXPIRE + 1))
    with freeze_time(past_time):
        with patch("src.utils.token.datetime") as mock_dt:
            mock_dt.now.return_value = past_time
            mock_dt.now.timezone = timezone.utc
            response = client.post(
                "/auth/verify-email",
                json={
                    "email": email,
                    "code": get_sent_mail(mock_mail)["Body"]
                }
            )
            refreshToken = client.cookies.get("refreshToken")
            assert refreshToken is not None
    client.cookies.set("refreshToken", refreshToken)
    response = client.post("/auth/refresh")
    assert response.status_code == 401
    assert response.json()["code"] == ErrorResponseCode.AUTH_TOKEN_EXPIRED

    # 4. Token not found in DB
    client.cookies.clear()
    response = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": password
        }
    )
    refreshToken = client.cookies.get("refreshToken")
    assert refreshToken is not None
    payload = verify_refresh_token(refreshToken)
    assert payload != JWTTokenStatus.INVALID
    assert payload != JWTTokenStatus.EXPIRED
    jti = payload.jti
    statement = select(Token).where(Token.jti_hash == hash_jti(jti))
    tok = session.exec(statement).one_or_none()
    assert tok is not None
    session.delete(tok)
    session.commit()
    response = client.post("/auth/refresh")
    assert response.status_code == 401
    assert response.json()["code"] == ErrorResponseCode.AUTH_TOKEN_INVALID

    # 5. Revoked token
    client.cookies.clear()
    response = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": password
        }
    )
    refreshToken = client.cookies.get("refreshToken")
    assert refreshToken is not None
    payload = verify_refresh_token(refreshToken)
    assert payload != JWTTokenStatus.INVALID
    assert payload != JWTTokenStatus.EXPIRED
    jti = payload.jti
    statement = select(Token).where(Token.jti_hash == hash_jti(jti))
    tok = session.exec(statement).one_or_none()
    assert tok is not None
    tok.revoked = True
    session.add(tok)
    session.commit()
    response = client.post("/auth/refresh")
    assert response.status_code == 403
    assert response.json()["code"] == ErrorResponseCode.AUTH_REVOKED

    # 6. Reuse detected
    tok.revoked = False
    session.add(tok)
    session.commit()
    client.cookies.set("refreshToken", refreshToken)
    response = client.post("/auth/refresh")
    assert response.status_code == 200
    client.cookies.set("refreshToken", refreshToken)
    response = client.post("/auth/refresh")
    assert response.status_code == 403
    assert response.json()["code"] == ErrorResponseCode.AUTH_REUSE_DETECTED
    
    # 7. DB expired
    client.cookies.clear()
    response = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": password
        }
    )
    refreshToken = client.cookies.get("refreshToken")
    assert refreshToken is not None
    payload = verify_refresh_token(refreshToken)
    assert payload != JWTTokenStatus.INVALID
    assert payload != JWTTokenStatus.EXPIRED
    jti = payload.jti
    statement = select(Token).where(Token.jti_hash == hash_jti(jti))
    tok = session.exec(statement).one_or_none()
    assert tok is not None
    tok.exp = tok.iat - timedelta(days=(REFRESH_TOKEN_EXPIRE + 1))
    session.add(tok)
    session.commit()
    response = client.post("/auth/refresh")
    assert response.status_code == 401
    assert response.json()["code"] == ErrorResponseCode.AUTH_TOKEN_EXPIRED

    # 8. Success
    client.cookies.clear()
    response = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": password
        }
    )
    assert response.status_code == 200
    response = client.post("/auth/refresh")
    assert response.status_code == 200

def _del(path: str):
    """Return a mutator that deletes agreements[path]."""
    def mutate(data: dict):
        del data[path]
    return mutate

def _nested_set(path: str, key: str, value):
    """Return a mutator that sets agreements[path][key] = value."""
    def mutate(data: dict):
        data[path][key] = value
    return mutate

class TestConsent:
    WRONG_VERSION = "2000-01-01"

    def _base_agreements(self):
        return {
            "termsOfService": {"version": AGREEABLE_CONSENT_VERSIONS["termsOfService"], "granted": True},
            "privacyRequired": {"version": AGREEABLE_CONSENT_VERSIONS["privacyRequired"], "granted": True},
            "age14": {"granted": True},
            "personalizedService": {"version": AGREEABLE_CONSENT_VERSIONS["personalizedService"], "granted": True},
            "marketing": {"version": AGREEABLE_CONSENT_VERSIONS["marketing"], "granted": True},
        }

    def test_consent_valid(self, authenticated_client: TestClient):
        req = authenticated_client.post("/auth/consent", json={"agreements": self._base_agreements()})
        assert req.status_code == 200

    @pytest.mark.parametrize("mutate,body_override", [
        # --- Required consents not granted ---
        pytest.param(_nested_set("termsOfService", "granted", False), None, id="tos_not_granted"),
        pytest.param(_nested_set("privacyRequired", "granted", False), None, id="privacy_not_granted"),
        pytest.param(_nested_set("age14", "granted", False), None, id="age14_not_granted"),

        # --- Wrong version ---
        pytest.param(_nested_set("termsOfService", "version", WRONG_VERSION), None, id="tos_wrong_version"),
        pytest.param(_nested_set("privacyRequired", "version", WRONG_VERSION), None, id="privacy_wrong_version"),
        pytest.param(_nested_set("personalizedService", "version", WRONG_VERSION), None, id="personalized_wrong_version"),
        pytest.param(_nested_set("marketing", "version", WRONG_VERSION), None, id="marketing_wrong_version"),

        # --- Missing fields ---
        pytest.param(_del("termsOfService"), None, id="missing_tos"),
        pytest.param(_del("privacyRequired"), None, id="missing_privacy"),
        pytest.param(_del("age14"), None, id="missing_age14"),
        pytest.param(_del("personalizedService"), None, id="missing_personalized"),
        pytest.param(_del("marketing"), None, id="missing_marketing"),

        # --- Wrong types ---
        pytest.param(_nested_set("age14", "granted", "yes"), None, id="granted_wrong_type"),
        pytest.param(_nested_set("termsOfService", "granted", "yes"), None, id="granted_wrong_type"),
        pytest.param(_nested_set("termsOfService", "version", 20260608), None, id="version_wrong_type"),

        # --- Malformed body (mutate unused, body_override takes precedence) ---
        pytest.param(None, {}, id="empty_body"),
        pytest.param(None, {"foo": "bar"}, id="missing_agreements_key"),
    ])

    def test_invalid_consent(self, authenticated_client: TestClient, mutate, body_override):
        if body_override is not None:
            body = body_override
        else:
            agreements = self._base_agreements()
            mutate(agreements)
            body = {"agreements": agreements}

        res = authenticated_client.post("/auth/consent", json=body)
        assert res.status_code == 400

valid_onboarding_data = {
    "name": "홍길동",
    "birth": "2001-01-01",
    "affiliation": "student",
    "school": "서울대학교",
    "department": "컴퓨터공학부",
    "company": None,
    "desiredRole": None,
    "affiliationDetail": None,
    "phone": "01000000000",
    "worry": ["진로", "이력"],
    "interest": ["컴퓨터", "AI"]
}

def test_onboarding_blocked_by_consent(authenticated_client: TestClient):
    response = authenticated_client.post("/auth/onboarding", json=valid_onboarding_data)
    assert response.status_code == 400
    assert len(response.json()["missing_consent"]) == 3
    req = authenticated_client.post("/auth/consent", json={"agreements": TestConsent()._base_agreements()})
    assert req.status_code == 200
    response = authenticated_client.post("/auth/onboarding", json=valid_onboarding_data)
    assert response.status_code == 200

def test_onboarding_valid_data(authenticated_client: TestClient):
    authenticated_client.post("/auth/consent", json={"agreements": TestConsent()._base_agreements()})
    response = authenticated_client.post("/auth/onboarding", json=valid_onboarding_data)
    assert response.status_code == 200

@pytest.mark.parametrize("override,expected_status", [
    # Missing required fields
    ({"name": None}, 400),
    ({"birth": None}, 400),
    ({"affiliation": None}, 400),
    ({"phone": None}, 400),
    ({"worry": None}, 400),
    ({"interest": None}, 400),

    # Invalid name
    ({"name": ""}, 400),

    # Invalid birth formats
    ({"birth": "01-01-2001"}, 400),    # wrong date format
    ({"birth": "not-a-date"}, 400),
    ({"birth": "2099-01-01"}, 400),    # future date
    ({"birth": 20010101}, 400),        # int instead of string

    # Invalid phone
    ({"phone": "010-0000-0000"}, 400), # dashes not allowed
    ({"phone": "0100000000"}, 400),    # too short (10 digits)
    ({"phone": "010000000000"}, 400),  # too long (12 digits)
    ({"phone": "abcdefghijk"}, 400),   # non-numeric

    # Invalid types for lists
    ({"worry": "진로"}, 400),           # string instead of list
    ({"interest": 123}, 400),          # int instead of list

    # Affiliation validation - STUDENT can't have company/desiredRole/affiliationDetail
    ({"affiliation": "student", "company": "SomeCompany"}, 400),
    ({"affiliation": "student", "desiredRole": "Engineer"}, 400),
    ({"affiliation": "student", "affiliationDetail": "Detail"}, 400),

    # Affiliation validation - EMPLOYED can't have school/department/desiredRole/affiliationDetail
    ({"affiliation": "employed", "school": "SomeSchool"}, 400),
    ({"affiliation": "employed", "department": "CS"}, 400),
    ({"affiliation": "employed", "desiredRole": "Engineer"}, 400),
    ({"affiliation": "employed", "affiliationDetail": "Detail"}, 400),

    # Affiliation validation - JOBSEEKER can't have school/department/company/affiliationDetail
    ({"affiliation": "jobseeker", "school": "SomeSchool"}, 400),
    ({"affiliation": "jobseeker", "department": "CS"}, 400),
    ({"affiliation": "jobseeker", "company": "SomeCompany"}, 400),
    ({"affiliation": "jobseeker", "affiliationDetail": "Detail"}, 400),

    # Affiliation validation - OTHER can't have school/department/company/desiredRole
    ({"affiliation": "other", "school": "SomeSchool"}, 400),
    ({"affiliation": "other", "department": "CS"}, 400),
    ({"affiliation": "other", "company": "SomeCompany"}, 400),
    ({"affiliation": "other", "desiredRole": "Engineer"}, 400),
])


def test_onboarding_invalid_data(authenticated_client: TestClient, override: dict[str, str | list[str] | int | None], expected_status: int):
    data = {**valid_onboarding_data, **{k: v for k, v in override.items() if v is not None}}
    # Remove key entirely if value is None (simulates missing field)
    for k, v in override.items():
        if v is None:
            data.pop(k, None)

    authenticated_client.post("/auth/consent", json={"agreements": TestConsent()._base_agreements()})
    response = authenticated_client.post("/auth/onboarding", json=data)
    assert response.status_code == expected_status
    assert response.json()["code"] == "INVALID_INPUT"


def test_onboarding_unauthenticated(client: TestClient):
    """Should fail without prior signup/verify"""
    response = client.post("/auth/onboarding", json=valid_onboarding_data)
    assert response.status_code == 401


def test_onboarding_duplicate(authenticated_client: TestClient):
    """Second onboarding attempt should fail"""
    authenticated_client.post("/auth/consent", json={"agreements": TestConsent()._base_agreements()})
    _ = authenticated_client.post("/auth/onboarding", json=valid_onboarding_data)
    response = authenticated_client.post("/auth/onboarding", json=valid_onboarding_data)
    assert response.status_code in (400, 409)

def test_logout_success(authenticated_client: TestClient):
    response = authenticated_client.post("/auth/logout")
    assert response.status_code == 200
    assert authenticated_client.cookies.get("refreshToken") is None
    assert authenticated_client.cookies.get("accessToken") is None

def test_logout_no_token(client: TestClient):
    response = client.post("/auth/logout")
    assert response.status_code == 401
    assert response.json()["code"] == ErrorResponseCode.AUTH_MISSING_COOKIES

def test_logout_token_not_found(authenticated_client: TestClient, session: Session):
    tok = session.exec(select(Token)).one()
    session.delete(tok)
    session.commit()
    response = authenticated_client.post("/auth/logout")
    assert response.status_code == 401
    assert response.json()["code"] == ErrorResponseCode.AUTH_TOKEN_INVALID

def test_logout_token_already_revoked(authenticated_client: TestClient, session: Session):
    tok = session.exec(select(Token)).one()
    tok.revoked = True
    session.add(tok)
    session.commit()
    response = authenticated_client.post("/auth/logout")
    assert response.status_code == 403
    assert response.json()["code"] == ErrorResponseCode.AUTH_REVOKED
    assert authenticated_client.cookies.get("refreshToken") is None
    assert authenticated_client.cookies.get("accessToken") is None

def test_logout_token_jti_manipulated(authenticated_client: TestClient, session: Session):
    tok = session.exec(select(Token)).one()
    tok.jti_hash = hash_jti(uuid4())
    session.add(tok)
    session.commit()
    response = authenticated_client.post("/auth/logout")
    assert response.status_code == 401
    assert response.json()["code"] == ErrorResponseCode.AUTH_TOKEN_INVALID

def test_me(authenticated_client: TestClient):
    response = authenticated_client.get("/auth/me")
    assert response.status_code == 200
    assert response.json()["data"]["account"]["email"] == email
    assert response.json()["data"]["onboarded"] == False
    assert response.json()["data"]["profile"] is None
    authenticated_client.post("/auth/consent", json={"agreements": TestConsent()._base_agreements()})
    _ = authenticated_client.post("/auth/onboarding", json=valid_onboarding_data)
    response = authenticated_client.get("/auth/me")
    assert response.status_code == 200
    assert response.json()["data"]["account"]["email"] == email
    assert response.json()["data"]["onboarded"] == True
    assert response.json()["data"]["profile"] is not None

def test_me_revoked_token(authenticated_client: TestClient, session: Session):
    tok = session.exec(select(Token)).one()
    tok.revoked = True
    session.add(tok)
    session.commit()
    response = authenticated_client.get("/auth/me")
    assert response.status_code == 403
    assert response.json()["code"] == ErrorResponseCode.AUTH_REVOKED
    assert authenticated_client.cookies.get("refreshToken") is None
    assert authenticated_client.cookies.get("accessToken") is None

def test_me_rotated_token(authenticated_client: TestClient, session: Session):
    tok = session.exec(select(Token)).one()
    tok.next = uuid4()
    session.add(tok)
    session.commit()
    response = authenticated_client.get("/auth/me")
    assert response.status_code == 403
    assert response.json()["code"] == ErrorResponseCode.AUTH_REUSE_DETECTED
    assert authenticated_client.cookies.get("refreshToken") is None
    assert authenticated_client.cookies.get("accessToken") is None

def test_me_after_logout(authenticated_client: TestClient):
    response = authenticated_client.post("/auth/logout")
    assert response.status_code == 200
    response = authenticated_client.get("/auth/me")
    assert response.status_code == 401
    assert response.json()["code"] == ErrorResponseCode.AUTH_MISSING_COOKIES