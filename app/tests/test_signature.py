import hashlib
import hmac
import json
from os import getenv
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient

INTERNAL_SECRET_KEY = "INTERNAL_SECRET"
INTERNAL_SECRET_FAKE = "internalkeyinternalkeyinternalkey"

def sign_body(body: dict[str, Any]):
    body_bytes = json.dumps(body, separators=(",", ":"), sort_keys=True, default=str).encode()
    return hmac.new(INTERNAL_SECRET_FAKE.encode(), body_bytes, hashlib.sha256).hexdigest()

def test_call_frontend(client: TestClient):
    with patch("src.utils.internal.getenv") as mock_getenv:
        def fake_env(key: str):
            return {
                INTERNAL_SECRET_KEY: INTERNAL_SECRET_FAKE
            }.get(key)

        mock_getenv.side_effect = fake_env

        body = {'analysis_id': 'e358547e-1adb-450a-b0a4-49cbc910ea68', 'result': {'summary': 'test result', 'schema_version': 'individual/v1.0'}}
        signature = sign_body(body)
        res = client.post(
            f"/{getenv("INTERNAL_ROUTE", "internal")}/individual/success",
            json=body,
            headers={"X-Signature": signature + "2"}
        )
        assert res.status_code == 403
        res = client.post(
            f"/{getenv("INTERNAL_ROUTE", "internal")}/individual/success",
            json=body,
            headers={"X-Signature": signature}
        )
        assert res.status_code == 404