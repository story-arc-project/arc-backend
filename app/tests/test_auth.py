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
from src.const import REFRESH_TOKEN_EXPIRE, VERIFICATION_MAX_ATTEMPTS
from src.db.models import Token
from src.utils.mail import send_mail
from src.enums import ErrorResponseCode, JWTTokenStatus


# Test data
email = "test@gmail.com"
password = "testpassword"


def get_sent_mail(mock_mail: MagicMock):
    sent_mail: MIMEMultipart = mock_mail.send_message.call_args[0][0]
    for part in sent_mail.walk():
        if part.get_content_type() == "text/plain" and not part.is_multipart():
            return {
                "To": sent_mail["To"],
                "Subject": sent_mail["Subject"],
                "Body": part.get_payload(decode=True).decode(
                    part.get_content_charset() or "utf-8"
                )
            }
    return {
        "To": sent_mail["To"],
        "Subject": sent_mail["Subject"],
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


def test_verification(client: TestClient, mock_mail: MagicMock):
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

        assert response.status_code == 401
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
    for _ in range(VERIFICATION_MAX_ATTEMPTS):
        response = client.post(
            "/auth/verify-email",
            json={
                "email": email,
                "code": "1234"
            }
        )

        assert response.status_code == 401
        assert response.cookies.get("accessToken") is None
        assert response.cookies.get("refreshToken") is None

        data = response.json()
        assert "remaining_attempts" in data
        remaining = data["remaining_attempts"]
        assert remaining >= 0
        if prev_remaining is not None:
            assert remaining == prev_remaining - 1
        prev_remaining = remaining

    # Final wrong attempt exhausts the code; remaining_attempts is 0, not negative
    response = client.post(
        "/auth/verify-email",
        json={
            "email": email,
            "code": "1234"
        }
    )

    assert response.status_code == 401
    assert response.cookies.get("accessToken") is None
    assert response.cookies.get("refreshToken") is None
    data = response.json()
    assert "remaining_attempts" in data
    assert data["remaining_attempts"] == 0

    # Correct code also fails now since attempts are exhausted
    response = client.post(
        "/auth/verify-email",
        json={
            "email": email,
            "code": code
        }
    )

    assert response.status_code == 401
    assert response.cookies.get("accessToken") is None
    assert response.cookies.get("refreshToken") is None
    data = response.json()
    assert "remaining_attempts" in data
    assert data["remaining_attempts"] == 0

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

def test_onboarding_valid_data(authenticated_client: TestClient):
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

    response = authenticated_client.post("/auth/onboarding", json=data)
    assert response.status_code == expected_status


def test_onboarding_unauthenticated(client: TestClient):
    """Should fail without prior signup/verify"""
    response = client.post("/auth/onboarding", json=valid_onboarding_data)
    assert response.status_code == 401


def test_onboarding_duplicate(authenticated_client: TestClient):
    """Second onboarding attempt should fail"""
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