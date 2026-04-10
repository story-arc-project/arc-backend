from fastapi.testclient import TestClient
from sqlmodel import Session, select

from src.enums import UserStatus
from src.db.models import User


def test_enum(session: Session, client: TestClient):
    assert UserStatus.UNVERIFIED == "unverified"
    email = "test@gmail.com"
    _ = client.post(
        "/auth/signup",
        json={
            "email": email,
            "password": "testpassword"
        }
    )
    statement = select(User).where(User.email == email)
    result = session.exec(statement).one()
    assert result.status == UserStatus.UNVERIFIED
    assert result.status == "unverified"