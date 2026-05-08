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
    body_bytes = json.dumps(body, separators=(",", ":")).encode()
    return hmac.new(INTERNAL_SECRET_FAKE.encode(), body_bytes, hashlib.sha256).hexdigest()

def test_call_frontend(client: TestClient):
    with patch("src.utils.internal.getenv") as mock_getenv:
        def fake_env(key: str):
            return {
                INTERNAL_SECRET_KEY: INTERNAL_SECRET_FAKE
            }.get(key)

        mock_getenv.side_effect = fake_env

        body = {'analysis_id': 'e358547e-1adb-450a-b0a4-49cbc910ea68', 'result': {'summary': 'test result'}}
        signature = sign_body(body)
        assert signature == "fce5f812c96a58d2b890e42e95f7e0618db8de7a187aace10b8b02537fc1ec0a"
        res = client.post(
            f"/{getenv("INTERNAL_ROUTE", "internal")}/individual/success",
            json=body,
            headers={"X-Signature": signature + "2"},
            timeout=10
        )
        assert res.status_code == 403
        res = client.post(
            f"/{getenv("INTERNAL_ROUTE", "internal")}/individual/success",
            json=body,
            headers={"X-Signature": signature},
            timeout=10
        )
        assert res.status_code == 404