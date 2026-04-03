from datetime import datetime, timedelta, timezone
from time import sleep
import pytest  
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from sqlalchemy.pool import NullPool
from unittest.mock import MagicMock, patch
from email.mime.multipart import MIMEMultipart
from testcontainers.postgres import PostgresContainer

from src.utils.token import hash_jti, verify_refresh_token
from src.const import REFRESH_TOKEN_EXPIRE
from src.db.models import Token
from src.main import app
from src.db.db import get_session
from src.utils.mail import send_mail
from src.enums import ErrorResponseCode, JWTTokenStatus


# Test data
email = "test@gmail.com"
password = "testpassword"


@pytest.fixture(name="session")  
def session_fixture():
    with PostgresContainer("postgres:16") as postgres:
        engine = create_engine(postgres.get_connection_url(), poolclass=NullPool)
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            yield session


@pytest.fixture
def client(session: Session):
    def override():
        with Session(session.get_bind()) as new_session:
            yield new_session
    
    app.dependency_overrides[get_session] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


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
    past_time = datetime.now(timezone.utc) - timedelta(minutes=REFRESH_TOKEN_EXPIRE + 1)
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
    tok.exp = tok.iat - timedelta(minutes=REFRESH_TOKEN_EXPIRE + 1)
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

@pytest.fixture
def authenticated_client(client: TestClient, mock_mail: MagicMock):
    _ = client.post("/auth/signup", json={"email": email, "password": password})
    response = client.post("/auth/verify-email", json={
        "email": email,
        "code": get_sent_mail(mock_mail)["Body"]
    })
    assert response.status_code == 200
    return client

valid_data = {
    "name": "홍길동",
    "birth": "2001-01-01",
    "education": "서울대학교",
    "phone": "01000000000",
    "worry": ["진로", "이력"],
    "interest": ["컴퓨터", "AI"]
}

@pytest.mark.parametrize("override,expected_status", [
    # Missing required fields
    ({"name": None}, 400),
    ({"birth": None}, 400),
    ({"phone": None}, 400),

    # Invalid formats
    ({"birth": "01-01-2001"}, 400),    # wrong date format
    ({"birth": "not-a-date"}, 400),
    ({"birth": "2099-01-01"}, 400),    # future date
    ({"phone": "010-0000-0000"}, 400), # dashes not allowed
    ({"phone": "0100000000"}, 400),    # too short
    ({"phone": "010000000000"}, 400),  # too long
    ({"phone": "abcdefghijk"}, 400),   # non-numeric

    # Empty values
    ({"name": ""}, 400),
    ({"education": ""}, 400),

    # Wrong types
    ({"worry": "진로"}, 400),           # string instead of list
    ({"interest": 123}, 400),
    ({"birth": 20010101}, 400),        # int instead of string
])

def test_onboarding_invalid_data(authenticated_client: TestClient, override: dict[str, str | list[str] | int | None], expected_status: int):
    data = {**valid_data, **{k: v for k, v in override.items() if v is not None}}
    # Remove key entirely if value is None (simulates missing field)
    for k, v in override.items():
        if v is None:
            data.pop(k, None)

    response = authenticated_client.post("/auth/onboarding", json=data)
    assert response.status_code == expected_status


def test_onboarding_unauthenticated(client: TestClient):
    """Should fail without prior signup/verify"""
    response = client.post("/auth/onboarding", json=valid_data)
    assert response.status_code in (401, 403)


def test_onboarding_duplicate(authenticated_client: TestClient):
    """Second onboarding attempt should fail"""
    _ = authenticated_client.post("/auth/onboarding", json=valid_data)
    response = authenticated_client.post("/auth/onboarding", json=valid_data)
    assert response.status_code in (400, 409)