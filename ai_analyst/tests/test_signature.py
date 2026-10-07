

import hashlib
import hmac
import json
from typing import Any
from unittest.mock import patch
from uuid import uuid4

from src.queue.tasks import sign_body


INTERNAL_SECRET_KEY = "INTERNAL_SECRET"
INTERNAL_SECRET_FAKE = "internalkeyinternalkeyinternalkey"

def verify_signature(body: dict[str, Any], signature: str):
    expected = hmac.new(
        INTERNAL_SECRET_FAKE.encode(),
        json.dumps(body, separators=(",", ":")).encode(),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)

def test_signature():
    with patch("src.queue.tasks.getenv") as mock_getenv:
        def fake_env(key: str):
            return {
                INTERNAL_SECRET_KEY: INTERNAL_SECRET_FAKE
            }.get(key)

        mock_getenv.side_effect = fake_env

        analysis_id = str(uuid4())
        data = {"summary": "test result"}
        body = {
            "analysis_id": analysis_id,
            "result": data
        }
        signature= sign_body(body)
        assert verify_signature(body, signature)