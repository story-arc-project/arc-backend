import pytest  
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool
from unittest.mock import MagicMock
from email.mime.multipart import MIMEMultipart

from src.db.models import User
from src.enums import UserStatus
from src.main import app
from src.db.db import get_session
from src.utils.mail import send_mail


# Test data
email = "test@gmail.com"
password = "testpassword"


@pytest.fixture(name="session")  
def session_fixture():  
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
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


def test_signup(client: TestClient):
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


def test_login(client: TestClient, session: Session):
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

    statement = select(User).where(User.email == email)
    user = session.exec(statement).one()
    user.status = UserStatus.VERIFIED
    session.add(user)
    session.commit()
    session.refresh(user)

    response = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": password
        }
    )

    assert response.status_code == 200