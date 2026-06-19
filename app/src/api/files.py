from fastapi import APIRouter, Depends
from src.api.models.exc import AppException, ErrorResponse
from src.api.models.base import FileMetadataPublic, PresignUploadData, SuccessResponse
from src.api.models.request import ConfirmUploadRequest, PresignUploadRequest
from src.api.models.response import FileListResponse, PresignUploadResponse
from src.const import EXPIRES_IN
from src.db.db import SessionDep
from src.db.models import FileMetadata
from src.enums import ErrorResponseCode
from src.utils.auth import check_auth
from src.utils.files import S3Dep
from src.utils.token import AccessTokenPayload
from sqlmodel import select
from typing import Annotated
import uuid

files_router = APIRouter()

@files_router.post("/presign", response_model=PresignUploadResponse)
async def presign_upload(body: PresignUploadRequest, session: SessionDep, s3: S3Dep, payload: Annotated[AccessTokenPayload, Depends(check_auth)]):
    # TODO: Implement allowed content types, max file size
    key = f"users/{payload.sub}/{uuid.uuid4()}"
    upload_url = s3.presign_upload(key=key)
    file_record = FileMetadata(
        user_id=payload.sub,
        key=key,
        filename=body.filename,
        content_type=body.content_type,
        size=body.size
    )
    session.add(file_record)
    session.commit()
    return PresignUploadResponse(
        message="Presign upload url generated.",
        data=PresignUploadData(
            key=key,
            upload_url=upload_url,
            expires_in=EXPIRES_IN
        )
    )

@files_router.post("/confirm")
async def confirm_upload(body: ConfirmUploadRequest, session: SessionDep, s3: S3Dep, payload: Annotated[AccessTokenPayload, Depends(check_auth)]):
    # TODO: Implement not confirmed file records cleanup
    file_record = session.exec(
        select(FileMetadata).where(
            FileMetadata.key == body.key,
            FileMetadata.user_id == payload.sub
        )
    ).one_or_none()
    if file_record is None:
        raise AppException(
            status_code=404,
            error=ErrorResponse(
                code=ErrorResponseCode.NOT_FOUND,
                message="File record not found"
            )
        )
    try:
        head = s3._client.head_object(Bucket=s3.settings.s3_bucket_name, Key=body.key)
    except s3._client.exceptions.ClientError:
        raise AppException(
            status_code=404,
            error=ErrorResponse(
                code=ErrorResponseCode.NOT_FOUND,
                message="File not found"
            )
        )
    actual_size = head["ContentLength"]
    actual_content_type = head.get("ContentType", "")
    if actual_size != file_record.size:
        raise AppException(
            status_code=400,
            error=ErrorResponse(
                code=ErrorResponseCode.METADATA_ERROR,
                message="File size does not match metadata"
            )
        )
    if actual_content_type != file_record.content_type:
        raise AppException(
            status_code=400,
            error=ErrorResponse(
                code=ErrorResponseCode.METADATA_ERROR,
                message="File content type does not match metadata"
            )
        )
    file_record.confirmed = True
    session.add(file_record)
    session.commit()
    return SuccessResponse(message="File confirmed")

@files_router.get("/", response_model=FileListResponse)
async def list_files(session: SessionDep, payload: Annotated[AccessTokenPayload, Depends(check_auth)]):
    files = session.exec(
        select(FileMetadata).where(
            FileMetadata.user_id == payload.sub,
            FileMetadata.confirmed == True
        )
    ).all()
    return FileListResponse(
        message="File list fetch success",
        data=[FileMetadataPublic.model_validate(file) for file in files]
    )