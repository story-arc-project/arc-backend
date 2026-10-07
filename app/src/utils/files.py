import boto3
from functools import lru_cache
from fastapi import Depends
from typing import Annotated
from src.const import UPLOAD_EXPIRES_IN, DOWNLOAD_EXPIRES_IN
from pydantic_settings import BaseSettings
from mypy_boto3_s3 import S3Client as BotoS3Client
from botocore.config import Config

class S3Settings(BaseSettings):
    aws_access_key_id: str
    aws_secret_access_key: str
    aws_region: str = "auto"            # use "auto" for R2
    s3_bucket_name: str
    s3_endpoint_url: str | None = None  # required for R2, None for AWS S3

@lru_cache
def get_s3_settings():
    return S3Settings()

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
    
    def presign_upload(self, key: str, expires_in: int = UPLOAD_EXPIRES_IN):
        return self._client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self.settings.s3_bucket_name,
                "Key": key,
            },
            ExpiresIn=expires_in
        )

    def presign_download(self, key: str, expires_in: int = DOWNLOAD_EXPIRES_IN):
        return self._client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.settings.s3_bucket_name,
                "Key": key
            },
            ExpiresIn=expires_in
        )
    
    def get_head(self, key: str):
        return self._client.head_object(Bucket=self.settings.s3_bucket_name, Key=key)
    
    def remove(self, key: str):
        self._client.delete_object(Bucket=self.settings.s3_bucket_name, Key=key)

def get_s3_client(settings: Annotated[S3Settings, Depends(get_s3_settings)]):
    return S3Client(settings)

S3Dep = Annotated[S3Client, Depends(get_s3_client)]