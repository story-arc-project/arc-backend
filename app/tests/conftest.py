from fastapi.testclient import TestClient
import pytest
from fakeredis import FakeRedis
from unittest.mock import MagicMock, patch
from sqlalchemy import text
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel, Session, create_engine
from testcontainers.minio import MinioContainer
from src.utils.files import S3Settings, S3Client, get_s3_client
from testcontainers.postgres import PostgresContainer
import os

from tests.const import TESTFRONT_HOST, TESTSERVER_HOST
os.environ["FRONTEND_HOSTS"] = f"https://{TESTFRONT_HOST}"

from tests.test_auth import get_sent_mail
from src.db.db import get_session
from src.main import app

@pytest.fixture(autouse=True)
def fake_redis():
    fake = FakeRedis(decode_responses=True)
    
    with patch("src.db.red.r", fake):
        yield fake

@pytest.fixture(scope="session")
def minio_container():
    with MinioContainer() as minio:
        yield minio

@pytest.fixture
def s3_settings(minio_container: MinioContainer):
    config = minio_container.get_config()
    return S3Settings(
        aws_access_key_id=config["access_key"],
        aws_secret_access_key=config["secret_key"],
        aws_region="us-east-1",
        s3_bucket_name="test-bucket",
        s3_endpoint_url=f"http://{config["endpoint"]}"
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
                "GMAIL": "test@gmail.com",
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


@pytest.fixture(name="session")  
def session_fixture():
    with PostgresContainer("pgvector/pgvector:pg16") as postgres:
        engine = create_engine(postgres.get_connection_url(), poolclass=NullPool)
        with engine.begin() as conn:
            _ = conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            yield session


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
    email = "test@gmail.com"
    password = "testpassword123"
    _ = client.post("/auth/signup", json={"email": email, "password": password})
    response = client.post("/auth/verify-email", json={
        "email": email,
        "code": get_sent_mail(mock_mail)["Body"]
    })
    assert response.status_code == 200
    assert client.cookies.get("refreshToken") is not None
    assert client.cookies.get("accessToken") is not None
    return client
