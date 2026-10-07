from uuid import uuid4
from fastapi.testclient import TestClient
import pytest
from fakeredis import FakeRedis
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import text
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel, Session, create_engine
from testcontainers.localstack import LocalStackContainer
from src.utils.files import S3Settings, S3Client, get_s3_client
from testcontainers.postgres import PostgresContainer
import os

from tests.const import AUTHENTICATED_EMAIL, TESTFRONT_HOST, TESTSERVER_HOST
os.environ["FRONTEND_HOSTS"] = f"https://{TESTFRONT_HOST}"
os.environ.setdefault("RATE_LIMIT_ANALYSIS_INDIVIDUAL", "10")
os.environ.setdefault("RATE_LIMIT_ANALYSIS_COMPREHENSIVE", "10")
os.environ.setdefault("RATE_LIMIT_ANALYSIS_KEYWORD", "10")
os.environ.setdefault("RATE_LIMIT_EXPORT_RESUME", "10")
os.environ.setdefault("RATE_LIMIT_EXPORT_COVER_LETTER", "10")

from tests.utils import generate_authenticated_user
from src.db.db import get_session
from src.main import app

@pytest.fixture(autouse=True)
def fake_redis():
    fake = FakeRedis(decode_responses=True)
    
    with patch("src.db.red.r", fake):
        yield fake

@pytest.fixture(scope="session")
def minio_container():
    with LocalStackContainer().with_services("s3") as minio:
        yield minio

@pytest.fixture
def s3_settings(minio_container: LocalStackContainer):
    endpoint_url = minio_container.get_url()
    return S3Settings(
        aws_access_key_id="test",
        aws_secret_access_key="test",
        aws_region="us-east-1",
        s3_bucket_name="test-bucket",
        s3_endpoint_url=endpoint_url,
    )

@pytest.fixture
def s3_client(s3_settings: S3Settings):
    client = S3Client(s3_settings)
    bucket_name = s3_settings.s3_bucket_name
    client._client.create_bucket(Bucket=bucket_name)
    yield client
    objects = client._client.list_objects(Bucket=bucket_name).get("Contents", [])
    for obj in objects:
        client._client.delete_object(Bucket=bucket_name, Key=obj["Key"])
    client._client.delete_bucket(Bucket=bucket_name)

@pytest.fixture(autouse=True)
def mock_mail():
    with patch("src.utils.mail.smtplib.SMTP") as mock_smtp, \
        patch("src.utils.mail.getenv") as mock_getenv:

        def fake_env(key: str):
            return {
                "GMAIL": AUTHENTICATED_EMAIL,
                "GMAIL_PASSWORD": "password"
            }.get(key)

        mock_getenv.side_effect = fake_env

        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        mock_server.send_message.return_value = {}

        yield mock_server

@pytest.fixture(autouse=True)
def mock_jwt_key():
    with patch("src.utils.token.getenv") as mock_getenv:
        def fake_env(key: str):
            return {
                "JWT_KEY": "fakejwtkeyfakejwtkeyfakejwtkeyfakejwtkey",
                "HMAC_KEY": "fakehmackeyfakehmackeyfakehmackeyfakehmackey"
            }.get(key)
        
        mock_getenv.side_effect = fake_env

        yield mock_getenv


@pytest.fixture(scope="session")
def db_engine():
    with PostgresContainer("pgvector/pgvector:pg16") as postgres:
        engine = create_engine(postgres.get_connection_url(), poolclass=NullPool)
        with engine.begin() as conn:
            _ = conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        SQLModel.metadata.create_all(engine)
        yield engine
        SQLModel.metadata.drop_all(engine)
        engine.dispose()


def clear_database(engine) -> None:
    table_names = []
    for table in SQLModel.metadata.sorted_tables:
        escaped_name = table.name.replace('"', '""')
        table_names.append(f'"{escaped_name}"')
    if table_names:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "TRUNCATE TABLE "
                    + ", ".join(table_names)
                    + " RESTART IDENTITY CASCADE"
                )
            )


@pytest.fixture(name="session")
def session_fixture(db_engine):
    clear_database(db_engine)
    try:
        with Session(db_engine) as session:
            yield session
    finally:
        clear_database(db_engine)


@pytest.fixture
def client(session: Session, s3_client: S3Client):
    def override():
        with Session(session.get_bind()) as new_session:
            yield new_session
    def override_s3():
        return s3_client
    
    app.dependency_overrides[get_session] = override
    app.dependency_overrides[get_s3_client] = override_s3
    yield TestClient(
        app,
        f"https://{TESTSERVER_HOST}",
        headers={
            "Origin": f"https://{TESTFRONT_HOST}"
        }
    )
    app.dependency_overrides.clear()

@pytest.fixture
def authenticated_client(client: TestClient, mock_mail: MagicMock):
    # Test data
    email = AUTHENTICATED_EMAIL
    password = "testpassword123"
    generate_authenticated_user(client, mock_mail, email, password)
    return client

@pytest.fixture
def other_authenticated_client(client: TestClient, mock_mail: MagicMock):
    other_client = TestClient(
        app,
        f"https://{TESTSERVER_HOST}",
        headers={"Origin": f"https://{TESTFRONT_HOST}"},
    )
    generate_authenticated_user(
        other_client,
        mock_mail,
        f"other-{uuid4()}@example.com",
        "testpassword123",
    )
    return other_client

@pytest.fixture(autouse=True)
def mock_ai_analyst(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("INTERNAL_SECRET", "default_secret")
    mock_response = MagicMock()
    mock_response.json.return_value = {"task_id": str(uuid4())}
    mock_response.raise_for_status.return_value = None
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response) as mock_post:
        yield mock_post

@pytest.fixture(autouse=True)
def override_credit_engine(session: Session):
    """
    Overrides the hardcoded `engine` in credit.py so that independent
    Session(engine) blocks use the testcontainer's database engine.
    """
    with patch("src.utils.credit.engine", session.bind):
        yield