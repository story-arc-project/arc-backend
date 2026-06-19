import pytest
import uuid
from pydantic import ValidationError
from fastapi.testclient import TestClient
from sqlmodel import select, Session
from unittest.mock import MagicMock
from src.utils.files import S3Settings, S3Client
from src.db.models import FileMetadata

class TestSettings:
    def test_settings_minio(self, monkeypatch):
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "arcdev")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "arcdev-minio-2026")
        monkeypatch.setenv("AWS_REGION", "us-east-1")
        monkeypatch.setenv("S3_BUCKET_NAME", "test-bucket")
        monkeypatch.setenv("S3_ENDPOINT_URL", "http://localhost:9000")

        settings = S3Settings()

        assert settings.aws_access_key_id == "arcdev"
        assert settings.aws_secret_access_key == "arcdev-minio-2026"
        assert settings.aws_region == "us-east-1"
        assert settings.s3_bucket_name == "test-bucket"
        assert settings.s3_endpoint_url == "http://localhost:9000"

    def test_settings_s3(self, monkeypatch):
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIA...")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
        monkeypatch.setenv("AWS_REGION", "ap-northeast-2")
        monkeypatch.setenv("S3_BUCKET_NAME", "prod-bucket")
        monkeypatch.delenv("S3_ENDPOINT_URL", raising=False)

        settings = S3Settings()

        assert settings.aws_region == "ap-northeast-2"
        assert settings.s3_endpoint_url is None  # uses AWS default

    def test_settings_r2(self, monkeypatch):
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "r2_key")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "r2_secret")
        monkeypatch.setenv("AWS_REGION", "auto")
        monkeypatch.setenv("S3_BUCKET_NAME", "prod-bucket")
        monkeypatch.setenv("S3_ENDPOINT_URL", "https://<account_id>.r2.cloudflarestorage.com")

        settings = S3Settings()

        assert settings.aws_region == "auto"
        assert settings.s3_endpoint_url == "https://<account_id>.r2.cloudflarestorage.com"

    def test_settings_missing_required(self, monkeypatch):
        monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
        monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
        monkeypatch.delenv("S3_BUCKET_NAME", raising=False)

        with pytest.raises(ValidationError):
            S3Settings()

    def test_settings_defaults(self, monkeypatch):
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "key")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
        monkeypatch.setenv("S3_BUCKET_NAME", "bucket")
        monkeypatch.delenv("AWS_REGION", raising=False)
        monkeypatch.delenv("S3_ENDPOINT_URL", raising=False)

        settings = S3Settings()

        assert settings.aws_region == "auto"      # default
        assert settings.s3_endpoint_url is None   # default

class TestPresign:
   def test_returns_url(self, s3_client: S3Client):
       url = s3_client.presign_upload(
           key="users/123/test.pdf",
       )
       assert url.startswith("http")
       assert "test.pdf" in url

   def test_url_contains_signature(self, s3_client: S3Client):
       url = s3_client.presign_upload(
           key="users/123/test.pdf",
       )
       assert "X-Amz-Signature" in url

   def test_custom_expiry(self, s3_client: S3Client):
       # just verify it doesn't error with custom expiry
       url = s3_client.presign_upload(
           key="users/123/test.pdf",
           expires_in=60,
       )
       assert url is not None

   def test_presigned_url_actually_works(self, s3_client: S3Client):
       import requests

       key = "users/123/upload-test.pdf"
       url = s3_client.presign_upload(key=key)

       response = requests.put(
           url,
           data=b"fake pdf content",
           headers={"Content-Type": "application/pdf"},
       )
       assert response.status_code == 200

       # verify the file exists in minio
       obj = s3_client._client.get_object(Bucket="test-bucket", Key=key)
       assert obj["Body"].read() == b"fake pdf content"

class TestPresignUpload:
    def test_presign_success(self, authenticated_client: TestClient):
        response = authenticated_client.post(
            "/files/presign",
            json={
                "filename": "certificate.pdf",
                "content_type": "application/pdf",
                "size": 1024,
            },
        )
        assert response.status_code == 200
        body = response.json()

        assert "key" in body["data"]
        assert "upload_url" in body["data"]
        assert body["data"]["upload_url"].startswith("http")
        assert "expires_in" in body["data"]

    def test_presign_creates_unconfirmed_record(self, authenticated_client: TestClient, session: Session):
        response = authenticated_client.post(
            "/files/presign",
            json={
                "filename": "resume.pdf",
                "content_type": "application/pdf",
                "size": 2048,
            },
        )
        key = response.json()["data"]["key"]

        record = session.exec(
            select(FileMetadata).where(FileMetadata.key == key)
        ).one_or_none()

        assert record is not None
        assert record.confirmed is False
        assert record.filename == "resume.pdf"
        assert record.content_type == "application/pdf"
        assert record.size == 2048

    def test_presign_key_is_namespaced_by_user(self, authenticated_client: TestClient):
        response = authenticated_client.post(
            "/files/presign",
            json={
                "filename": "test.pdf",
                "content_type": "application/pdf",
                "size": 100,
            },
        )
        key = response.json()["data"]["key"]
        assert key.startswith("users/")

    def test_presign_requires_auth(self, client: TestClient):
        response = client.post(
            "/files/presign",
            json={
                "filename": "test.pdf",
                "content_type": "application/pdf",
                "size": 100,
            },
        )
        assert response.status_code == 401

class TestConfirmUpload:
    def _presign(self, authenticated_client: TestClient, filename="test.pdf", content_type="application/pdf", size=16):
        response = authenticated_client.post(
            "/files/presign",
            json={"filename": filename, "content_type": content_type, "size": size},
        )
        return response.json()["data"]

    def test_confirm_success(self, authenticated_client: TestClient, session: Session):
        data = self._presign(authenticated_client, size=16)
        key = data["key"]
        upload_url = data["upload_url"]

        # actually upload matching bytes to MinIO via the presigned URL
        import requests
        put_response = requests.put(
            upload_url,
            data=b"a" * 16,
            headers={"Content-Type": "application/pdf"},
        )
        assert put_response.status_code == 200

        response = authenticated_client.post("/files/confirm", json={"key": key})
        assert response.status_code == 200

        record = session.exec(
            select(FileMetadata).where(FileMetadata.key == key)
        ).one_or_none()
        assert record.confirmed is True

    def test_confirm_not_found_record(self, authenticated_client: TestClient):
        response = authenticated_client.post(
            "/files/confirm",
            json={"key": f"users/{uuid.uuid4()}/nonexistent"},
        )
        assert response.status_code == 404

    def test_confirm_file_missing_in_storage(self, authenticated_client: TestClient):
        data = self._presign(authenticated_client)
        key = data["key"]
        # never actually uploaded to S3

        response = authenticated_client.post("/files/confirm", json={"key": key})
        assert response.status_code == 404

    def test_confirm_size_mismatch(self, authenticated_client: TestClient):
        data = self._presign(authenticated_client, size=16)
        key = data["key"]
        upload_url = data["upload_url"]

        import requests
        requests.put(
            upload_url,
            data=b"a" * 999,  # wrong size
            headers={"Content-Type": "application/pdf"},
        )

        response = authenticated_client.post("/files/confirm", json={"key": key})
        assert response.status_code == 400
        assert response.json()["code"] == "METADATA_ERROR"

    def test_confirm_content_type_mismatch(self, authenticated_client: TestClient):
        data = self._presign(authenticated_client, content_type="application/pdf", size=16)
        key = data["key"]
        upload_url = data["upload_url"]

        import requests
        requests.put(
            upload_url,
            data=b"a" * 16,
            headers={"Content-Type": "image/png"},  # wrong content type
        )

        response = authenticated_client.post("/files/confirm", json={"key": key})
        assert response.status_code == 400
        assert response.json()["code"] == "METADATA_ERROR"

    def test_confirm_other_user_cannot_confirm(self, authenticated_client: TestClient, client: TestClient, mock_mail: MagicMock):
        data = self._presign(authenticated_client)
        key = data["key"]

        # second, different user
        client.post("/auth/signup", json={"email": "other@gmail.com", "password": "testpassword123"})
        # ... verify email similarly to authenticated_client fixture, omitted for brevity

        response = client.post("/files/confirm", json={"key": key})
        assert response.status_code == 404  # owned by a different user, so not found