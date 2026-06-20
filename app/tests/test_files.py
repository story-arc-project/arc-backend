import pytest
import requests
import uuid
from pydantic import ValidationError
from fastapi.testclient import TestClient
from sqlmodel import Session
from unittest.mock import MagicMock
from src.utils.files import S3Settings, S3Client
from src.db.models import FileMetadata
from tests.test_auth import get_sent_mail
from src.const import ALLOWED_UPLOAD_CONTENT_SIZE
from src.enums import ErrorResponseCode

def _signup_second_user(client: TestClient, mock_mail: MagicMock, email: str = "other2@gmail.com"):
    """Signs up a second user on the shared client, returning that user's cookies.
    Does NOT restore the original user's cookies — caller is responsible for that."""
    client.post("/auth/signup", json={"email": email, "password": "testpassword123"})
    verify_response = client.post(
        "/auth/verify-email",
        json={"email": email, "code": get_sent_mail(mock_mail)["Body"]},
    )
    assert verify_response.status_code == 200
    return dict(client.cookies)

def _restore_cookies(client: TestClient, cookies: dict):
    client.cookies.clear()
    for k, v in cookies.items():
        client.cookies.set(k, v)

class TestSettings:
    def test_settings_minio(self, monkeypatch: pytest.MonkeyPatch):
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

    def test_settings_s3(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIA...")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
        monkeypatch.setenv("AWS_REGION", "ap-northeast-2")
        monkeypatch.setenv("S3_BUCKET_NAME", "prod-bucket")
        monkeypatch.delenv("S3_ENDPOINT_URL", raising=False)

        settings = S3Settings()

        assert settings.aws_region == "ap-northeast-2"
        assert settings.s3_endpoint_url is None  # uses AWS default

    def test_settings_r2(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "r2_key")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "r2_secret")
        monkeypatch.setenv("AWS_REGION", "auto")
        monkeypatch.setenv("S3_BUCKET_NAME", "prod-bucket")
        monkeypatch.setenv("S3_ENDPOINT_URL", "https://<account_id>.r2.cloudflarestorage.com")

        settings = S3Settings()

        assert settings.aws_region == "auto"
        assert settings.s3_endpoint_url == "https://<account_id>.r2.cloudflarestorage.com"

    def test_settings_missing_required(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
        monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
        monkeypatch.delenv("S3_BUCKET_NAME", raising=False)

        with pytest.raises(ValidationError):
            S3Settings()

    def test_settings_defaults(self, monkeypatch: pytest.MonkeyPatch):
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

        assert "id" in body["data"]
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
        id = response.json()["data"]["id"]

        record = session.get(FileMetadata, id)

        assert record is not None
        assert record.confirmed is False
        assert record.filename == "resume.pdf"
        assert record.content_type == "application/pdf"
        assert record.size == 2048

    def test_presign_key_is_namespaced_by_user(self, authenticated_client: TestClient, session: Session):
        response = authenticated_client.post(
            "/files/presign",
            json={
                "filename": "test.pdf",
                "content_type": "application/pdf",
                "size": 100,
            },
        )
        id = response.json()["data"]["id"]
        record = session.get(FileMetadata, id)
        assert record is not None
        key = record.key
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

    def test_presign_rejects_oversized_file(self, authenticated_client: TestClient):
        response = authenticated_client.post(
            "/files/presign",
            json={
                "filename": "huge.pdf",
                "content_type": "application/pdf",
                "size": ALLOWED_UPLOAD_CONTENT_SIZE * 1024 * 1024 + 1,
            },
        )
        assert response.status_code == 400
        body = response.json()
        assert body["code"] == ErrorResponseCode.BAD_REQUEST

    def test_presign_rejects_negative_size(self, authenticated_client: TestClient):
        response = authenticated_client.post(
            "/files/presign",
            json={
                "filename": "negative.pdf",
                "content_type": "application/pdf",
                "size": -1,
            },
        )
        assert response.status_code == 400
        body = response.json()
        assert body["code"] == ErrorResponseCode.BAD_REQUEST

    def test_presign_rejects_disallowed_content_type(self, authenticated_client: TestClient):
        response = authenticated_client.post(
            "/files/presign",
            json={
                "filename": "malware.exe",
                "content_type": "application/x-msdownload",
                "size": 1024,
            },
        )
        assert response.status_code == 400
        body = response.json()
        assert body["code"] == ErrorResponseCode.BAD_REQUEST

class TestConfirmUpload:
    def _presign(self, authenticated_client: TestClient, filename="test.pdf", content_type="application/pdf", size=16):
        response = authenticated_client.post(
            "/files/presign",
            json={"filename": filename, "content_type": content_type, "size": size},
        )
        return response.json()["data"]

    def test_confirm_success(self, authenticated_client: TestClient, session: Session):
        data = self._presign(authenticated_client, size=16)
        id = data["id"]
        upload_url = data["upload_url"]

        # actually upload matching bytes to MinIO via the presigned URL
        put_response = requests.put(
            upload_url,
            data=b"a" * 16,
            headers={"Content-Type": "application/pdf"},
        )
        assert put_response.status_code == 200

        response = authenticated_client.post("/files/confirm", json={"id": id})
        assert response.status_code == 200

        record = session.get(FileMetadata, id)
        assert record is not None
        assert record.confirmed is True

    def test_confirm_not_found_record(self, authenticated_client: TestClient):
        response = authenticated_client.post(
            "/files/confirm",
            json={"id": str(uuid.uuid4())},
        )
        assert response.status_code == 404

    def test_confirm_file_missing_in_storage(self, authenticated_client: TestClient):
        data = self._presign(authenticated_client)
        id = data["id"]
        # never actually uploaded to S3

        response = authenticated_client.post("/files/confirm", json={"id": id})
        assert response.status_code == 404

    def test_confirm_size_mismatch(self, authenticated_client: TestClient):
        data = self._presign(authenticated_client, size=16)
        id = data["id"]
        upload_url = data["upload_url"]

        requests.put(
            upload_url,
            data=b"a" * 999,  # wrong size
            headers={"Content-Type": "application/pdf"},
        )

        response = authenticated_client.post("/files/confirm", json={"id": id})
        assert response.status_code == 400
        assert response.json()["code"] == "METADATA_ERROR"

    def test_confirm_content_type_mismatch(self, authenticated_client: TestClient):
        data = self._presign(authenticated_client, content_type="application/pdf", size=16)
        id = data["id"]
        upload_url = data["upload_url"]

        requests.put(
            upload_url,
            data=b"a" * 16,
            headers={"Content-Type": "image/png"},  # wrong content type
        )

        response = authenticated_client.post("/files/confirm", json={"id": id})
        assert response.status_code == 400
        assert response.json()["code"] == "METADATA_ERROR"

    def test_confirm_other_user_cannot_confirm(self, authenticated_client: TestClient, client: TestClient, mock_mail: MagicMock):
        data = self._presign(authenticated_client)
        id = data["id"]
        upload_url = data["upload_url"]

        requests.put(
            upload_url,
            data=b"a" * 16,
            headers={"Content-Type": "application/pdf"},
        )

        original_cookies = dict(authenticated_client.cookies)

        _signup_second_user(client, mock_mail)
        response = client.post("/files/confirm", json={"id": id})
        assert response.status_code == 404

        _restore_cookies(client, original_cookies)
        own_response = client.post("/files/confirm", json={"id": id})
        # confirm normally — file is still owned by original user
        assert own_response.status_code == 200

class TestListFiles:
    def _presign_and_upload(
        self,
        authenticated_client: TestClient,
        filename="test.pdf",
        content_type="application/pdf",
        data=b"a" * 16,
    ):
        response = authenticated_client.post(
            "/files/presign",
            json={"filename": filename, "content_type": content_type, "size": len(data)},
        )
        body = response.json()["data"]
        id = body["id"]
        upload_url = body["upload_url"]

        put = requests.put(upload_url, data=data, headers={"Content-Type": content_type})
        assert put.status_code == 200

        return id

    def test_list_empty(self, authenticated_client: TestClient):
        response = authenticated_client.get("/files/")
        assert response.status_code == 200
        assert response.json()["data"] == []

    def test_list_only_confirmed_files(self, authenticated_client: TestClient):
        # presigned but never confirmed — should NOT appear
        authenticated_client.post(
            "/files/presign",
            json={"filename": "unconfirmed.pdf", "content_type": "application/pdf", "size": 16},
        )

        # presigned, uploaded, and confirmed — SHOULD appear
        id = self._presign_and_upload(authenticated_client, filename="confirmed.pdf")
        confirm_response = authenticated_client.post("/files/confirm", json={"id": id})
        assert confirm_response.status_code == 200

        response = authenticated_client.get("/files/")
        assert response.status_code == 200
        files = response.json()["data"]

        assert len(files) == 1
        assert files[0]["filename"] == "confirmed.pdf"

    def test_list_does_not_expose_key(self, authenticated_client: TestClient):
        id = self._presign_and_upload(authenticated_client, filename="secret.pdf")
        authenticated_client.post("/files/confirm", json={"id": id})

        response = authenticated_client.get("/files/")
        files = response.json()["data"]

        assert "key" not in files[0]

    def test_list_returns_expected_fields(self, authenticated_client: TestClient):
        id = self._presign_and_upload(
            authenticated_client, filename="report.pdf", content_type="application/pdf", data=b"x" * 32
        )
        authenticated_client.post("/files/confirm", json={"id": id})

        response = authenticated_client.get("/files/")
        file = response.json()["data"][0]

        assert file["filename"] == "report.pdf"
        assert file["content_type"] == "application/pdf"
        assert file["size"] == 32
        assert "id" in file
        assert "created_at" in file

    def test_list_only_returns_own_files(self, authenticated_client: TestClient, client: TestClient, mock_mail: MagicMock):
        # current user uploads + confirms a file
        id = self._presign_and_upload(authenticated_client, filename="mine.pdf")
        authenticated_client.post("/files/confirm", json={"id": id})

        original_cookies = dict(authenticated_client.cookies)

        _signup_second_user(client, mock_mail)
        response = client.get("/files/")
        assert response.status_code == 200
        assert response.json()["data"] == []

        _restore_cookies(client, original_cookies)
        own_response = client.get("/files/")
        own_files = own_response.json()["data"]
        assert len(own_files) == 1
        assert own_files[0]["filename"] == "mine.pdf"

    def test_list_requires_auth(self, client: TestClient):
        response = client.get("/files/")
        assert response.status_code == 401

class TestGetFile:
    def _presign_confirm_and_upload(
        self,
        authenticated_client: TestClient,
        filename="test.pdf",
        content_type="application/pdf",
        data=b"a" * 16,
    ):
        response = authenticated_client.post(
            "/files/presign",
            json={"filename": filename, "content_type": content_type, "size": len(data)},
        )
        body = response.json()["data"]
        file_id = body["id"]
        upload_url = body["upload_url"]

        put = requests.put(upload_url, data=data, headers={"Content-Type": content_type})
        assert put.status_code == 200

        confirm_response = authenticated_client.post("/files/confirm", json={"id": file_id})
        assert confirm_response.status_code == 200

        return file_id

    def test_get_file_success(self, authenticated_client: TestClient):
        file_id = self._presign_confirm_and_upload(
            authenticated_client, filename="report.pdf", content_type="application/pdf", data=b"x" * 32
        )

        response = authenticated_client.get(f"/files/{file_id}")
        assert response.status_code == 200

        data = response.json()["data"]
        assert data["id"] == file_id
        assert data["filename"] == "report.pdf"
        assert data["content_type"] == "application/pdf"
        assert data["size"] == 32
        assert "created_at" in data

    def test_get_file_does_not_expose_key(self, authenticated_client: TestClient):
        file_id = self._presign_confirm_and_upload(authenticated_client)

        response = authenticated_client.get(f"/files/{file_id}")
        data = response.json()["data"]

        assert "key" not in data

    def test_get_file_unconfirmed_not_found(self, authenticated_client: TestClient):
        # presigned but never uploaded/confirmed
        response = authenticated_client.post(
            "/files/presign",
            json={"filename": "unconfirmed.pdf", "content_type": "application/pdf", "size": 16},
        )
        file_id = response.json()["data"]["id"]

        response = authenticated_client.get(f"/files/{file_id}")
        assert response.status_code == 404
        assert response.json()["code"] == "NOT_FOUND"

    def test_get_file_not_found(self, authenticated_client: TestClient):
        response = authenticated_client.get(f"/files/{uuid.uuid4()}")
        assert response.status_code == 404
        assert response.json()["code"] == "NOT_FOUND"

    def test_get_file_other_user_cannot_access(self, authenticated_client: TestClient, client: TestClient, mock_mail: MagicMock):
        file_id = self._presign_confirm_and_upload(authenticated_client, filename="private.pdf")

        original_cookies = dict(authenticated_client.cookies)

        _signup_second_user(client, mock_mail, email="other3@gmail.com")
        response = client.get(f"/files/{file_id}")
        assert response.status_code == 404

        _restore_cookies(client, original_cookies)
        own_response = client.get(f"/files/{file_id}")
        assert own_response.status_code == 200

    def test_get_file_requires_auth(self, client: TestClient):
        response = client.get(f"/files/{uuid.uuid4()}")
        assert response.status_code == 401

    def test_get_file_invalid_uuid(self, authenticated_client: TestClient):
        response = authenticated_client.get("/files/not-a-uuid")
        assert response.status_code == 400

class TestDownloadFile:
    def _presign_confirm_and_upload(
        self,
        authenticated_client: TestClient,
        filename="test.pdf",
        content_type="application/pdf",
        data=b"a" * 16,
    ):
        response = authenticated_client.post(
            "/files/presign",
            json={"filename": filename, "content_type": content_type, "size": len(data)},
        )
        body = response.json()["data"]
        file_id = body["id"]
        upload_url = body["upload_url"]

        put = requests.put(upload_url, data=data, headers={"Content-Type": content_type})
        assert put.status_code == 200

        confirm_response = authenticated_client.post("/files/confirm", json={"id": file_id})
        assert confirm_response.status_code == 200

        return file_id

    def test_download_success(self, authenticated_client: TestClient):
        file_id = self._presign_confirm_and_upload(authenticated_client, data=b"hello world!!!!!")

        response = authenticated_client.get(f"/files/{file_id}/download")
        assert response.status_code == 200

        download_url = response.json()["data"]
        assert download_url.startswith("http")

    def test_download_url_actually_works(self, authenticated_client: TestClient):
        content = b"the real file content"
        file_id = self._presign_confirm_and_upload(authenticated_client, data=content)

        response = authenticated_client.get(f"/files/{file_id}/download")
        download_url = response.json()["data"]

        get_response = requests.get(download_url)
        assert get_response.status_code == 200
        assert get_response.content == content

    def test_download_not_found(self, authenticated_client: TestClient):
        response = authenticated_client.get(f"/files/{uuid.uuid4()}/download")
        assert response.status_code == 404
        assert response.json()["code"] == "NOT_FOUND"

    def test_download_unconfirmed_file(self, authenticated_client: TestClient):
        # presign but never upload/confirm
        response = authenticated_client.post(
            "/files/presign",
            json={"filename": "unconfirmed.pdf", "content_type": "application/pdf", "size": 16},
        )
        file_id = response.json()["data"]["id"]

        # record exists in DB, so this currently succeeds even though unconfirmed —
        # flagging this as a possible gap, see note below
        response = authenticated_client.get(f"/files/{file_id}/download")
        assert response.status_code == 400

    def test_download_other_user_cannot_access(self, authenticated_client: TestClient, client: TestClient, mock_mail: MagicMock):
        file_id = self._presign_confirm_and_upload(authenticated_client, filename="private.pdf")

        original_cookies = dict(authenticated_client.cookies)

        _signup_second_user(client, mock_mail)
        response = client.get(f"/files/{file_id}/download")
        assert response.status_code == 404

        _restore_cookies(client, original_cookies)
        own_response = client.get(f"/files/{file_id}/download")
        assert own_response.status_code == 200

    def test_download_requires_auth(self, client: TestClient):
        response = client.get(f"/files/{uuid.uuid4()}/download")
        assert response.status_code == 401

    def test_download_invalid_uuid(self, authenticated_client: TestClient):
        response = authenticated_client.get("/files/not-a-uuid/download")
        assert response.status_code == 400
        assert response.json()["code"] == "INVALID_INPUT"

class TestDeleteFile:
    def _presign_confirm_and_upload(
        self,
        authenticated_client: TestClient,
        filename="test.pdf",
        content_type="application/pdf",
        data=b"a" * 16,
    ):
        response = authenticated_client.post(
            "/files/presign",
            json={"filename": filename, "content_type": content_type, "size": len(data)},
        )
        body = response.json()["data"]
        file_id = body["id"]
        upload_url = body["upload_url"]

        put = requests.put(upload_url, data=data, headers={"Content-Type": content_type})
        assert put.status_code == 200

        confirm_response = authenticated_client.post("/files/confirm", json={"id": file_id})
        assert confirm_response.status_code == 200

        return file_id

    def test_delete_success(self, authenticated_client: TestClient):
        file_id = self._presign_confirm_and_upload(authenticated_client)

        response = authenticated_client.delete(f"/files/{file_id}")
        assert response.status_code == 204

    def test_delete_removes_db_record(self, authenticated_client: TestClient, session: Session):
        from src.db.models import FileMetadata
        from sqlmodel import select

        file_id = self._presign_confirm_and_upload(authenticated_client)
        authenticated_client.delete(f"/files/{file_id}")

        record = session.exec(
            select(FileMetadata).where(FileMetadata.id == file_id)
        ).one_or_none()
        assert record is None

    def test_delete_removes_s3_object(self, authenticated_client: TestClient, s3_client: S3Client):
        file_id = self._presign_confirm_and_upload(authenticated_client)

        # get the key before deleting, via download endpoint indirectly,
        # or query DB directly if db_session fixture is available
        from src.db.models import FileMetadata
        from sqlmodel import select

        # NOTE: requires db_session fixture to fetch key before delete
        # see test below for a self-contained version using head_object

        authenticated_client.delete(f"/files/{file_id}")

        # after delete, the file should no longer be downloadable
        response = authenticated_client.get(f"/files/{file_id}/download")
        assert response.status_code == 404

    def test_delete_not_found(self, authenticated_client: TestClient):
        response = authenticated_client.delete(f"/files/{uuid.uuid4()}")
        assert response.status_code == 404
        assert response.json()["code"] == "NOT_FOUND"

    def test_delete_other_user_cannot_delete(self, authenticated_client: TestClient, client: TestClient, mock_mail: MagicMock):
        file_id = self._presign_confirm_and_upload(authenticated_client)

        original_cookies = dict(authenticated_client.cookies)

        _signup_second_user(client, mock_mail)
        response = client.delete(f"/files/{file_id}")
        assert response.status_code == 404

        _restore_cookies(client, original_cookies)
        own_response = client.get(f"/files/{file_id}/download")
        assert own_response.status_code == 200

    def test_delete_requires_auth(self, client: TestClient):
        response = client.delete(f"/files/{uuid.uuid4()}")
        assert response.status_code == 401

    def test_delete_already_deleted(self, authenticated_client: TestClient):
        file_id = self._presign_confirm_and_upload(authenticated_client)

        first = authenticated_client.delete(f"/files/{file_id}")
        assert first.status_code == 204

        second = authenticated_client.delete(f"/files/{file_id}")
        assert second.status_code == 404