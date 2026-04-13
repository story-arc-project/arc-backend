

import hashlib
import hmac
import json
from os import getenv
from typing import Any
from uuid import uuid4

from src.queue.tasks import sign_body


INTERNAL_SECRET_KEY = "INTERNAL_SECRET"

def verify_signature(body: dict[str, Any], signature: str):
    key = getenv(INTERNAL_SECRET_KEY)
    if key is None:
        raise ValueError("Internal secret not set.")
    expected = hmac.new(
        key.encode(),
        json.dumps(body, separators=(",", ":")).encode(),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)

def test_signature():
    analysis_id = str(uuid4())
    data = {"summary": "test result"}
    body = {
        "analysis_id": analysis_id,
        "result": data
    }
    signature= sign_body(body)
    assert verify_signature(body, signature)