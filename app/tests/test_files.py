import pytest
from pydantic import ValidationError
from src.utils.files import S3Settings

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

class TestPresignUpload:
   def test_returns_url(self, s3_client):
       url = s3_client.presign_upload(
           key="users/123/test.pdf",
           content_type="application/pdf",
       )
       assert url.startswith("http")
       assert "test.pdf" in url

   def test_url_contains_signature(self, s3_client):
       url = s3_client.presign_upload(
           key="users/123/test.pdf",
           content_type="application/pdf",
       )
       assert "X-Amz-Signature" in url

   def test_custom_expiry(self, s3_client):
       # just verify it doesn't error with custom expiry
       url = s3_client.presign_upload(
           key="users/123/test.pdf",
           content_type="application/pdf",
           expires_in=60,
       )
       assert url is not None

   def test_presigned_url_actually_works(self, s3_client):
       import requests

       key = "users/123/upload-test.pdf"
       url = s3_client.presign_upload(key=key, content_type="application/pdf")

       response = requests.put(
           url,
           data=b"fake pdf content",
           headers={"Content-Type": "application/pdf"},
       )
       assert response.status_code == 200

       # verify the file exists in minio
       obj = s3_client._client.get_object(Bucket="test-bucket", Key=key)
       assert obj["Body"].read() == b"fake pdf content"