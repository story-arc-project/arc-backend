from pydantic_settings import BaseSettings

class S3Settings(BaseSettings):
    aws_access_key_id: str
    aws_secret_access_key: str
    aws_region: str = "auto"            # use "auto" for R2
    s3_bucket_name: str
    s3_endpoint_url: str | None = None  # required for R2, None for AWS S3