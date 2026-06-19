import boto3
from pydantic_settings import BaseSettings
from mypy_boto3_s3 import S3Client as BotoS3Client
from botocore.config import Config

class S3Settings(BaseSettings):
    aws_access_key_id: str
    aws_secret_access_key: str
    aws_region: str = "auto"            # use "auto" for R2
    s3_bucket_name: str
    s3_endpoint_url: str | None = None  # required for R2, None for AWS S3

class S3Client:
    def __init__(self, settings: S3Settings):
        self.settings = settings
        self._client: BotoS3Client = boto3.client(
            "s3",
            region_name=self.settings.aws_region,
            aws_access_key_id=self.settings.aws_access_key_id,
            aws_secret_access_key=self.settings.aws_secret_access_key,
            endpoint_url=self.settings.s3_endpoint_url,
            config=Config(signature_version="s3v4")
        )
    
    def presign_upload(self, key: str, content_type: str, expires_in: int = 300):
        return self._client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self.settings.s3_bucket_name,
                "Key": key,
                "ContentType": content_type
            },
            ExpiresIn=expires_in
        )