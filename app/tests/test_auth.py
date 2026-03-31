import pytest  
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from src.db.models import User
from src.enums import UserStatus
from src.main import app
from src.db.db import get_session


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