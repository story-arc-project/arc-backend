from fastapi import APIRouter, Depends
from src.api.models.base import PresignUploadData
from src.api.models.request import PresignUploadRequest
from src.api.models.response import PresignUploadResponse
from src.const import EXPIRES_IN
from src.db.db import SessionDep
from src.db.models import FileMetadata
from src.utils.auth import check_auth
from src.utils.files import S3Dep
from src.utils.token import AccessTokenPayload
from typing import Annotated
import uuid

files_router = APIRouter()

@files_router.post("/presign", response_model=PresignUploadResponse)
async def files_presign(body: PresignUploadRequest, session: SessionDep, s3: S3Dep, payload: Annotated[AccessTokenPayload, Depends(check_auth)]):
    # TODO: Implement allowed content types, max file size
    key = f"users/{payload.sub}/{uuid.uuid4()}"
    upload_url = s3.presign_upload(
        key=key,
        content_type=body.content_type
    )
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