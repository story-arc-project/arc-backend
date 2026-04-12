import hashlib
import hmac
import json
from os import getenv
from typing import Any
from fastapi import APIRouter, HTTPException, Request

from src.db.db import SessionDep

INTERNAL_SECRET_KEY = "INTERNAL_SECRET"

internal_router = APIRouter()

def verify_signature(body: dict[str, Any], signature: str):
    key = getenv(INTERNAL_SECRET_KEY)
    if key is None:
        raise ValueError("Internal secret not set.")
    expected = hmac.new(
        INTERNAL_SECRET_KEY.encode(),
        json.dumps(body, separators=(",", ":")).encode(),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)

@internal_router.post("/individual/complete")
async def complete_individual(request: Request, session: SessionDep):
    body = await request.json()
    signature = request.headers.get("X-Signature")
    if not signature or not verify_signature(body, signature):
        raise HTTPException(status_code=403)
    # TODO: add logic
    pass