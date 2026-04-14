import hashlib
import hmac
import json
from os import getenv
from typing import Any
import requests
from src.queue.celery_app import celery
from src.ai.individual import main as individual

FRONTEND_API_URL = "http://app:8000"
INTERNAL_SECRET_KEY = "INTERNAL_SECRET"

def sign_body(body: dict[str, Any]):
    key = getenv(INTERNAL_SECRET_KEY)
    if key is None:
        raise ValueError("Internal secret not set.")
    body_bytes = json.dumps(body, separators=(",", ":")).encode()
    return hmac.new(key.encode(), body_bytes, hashlib.sha256).hexdigest()

def call_frontend(endpoint: str, body: dict[str, Any]):
    response = requests.post(
        f"{FRONTEND_API_URL}{endpoint}",
        json=body,
        headers={"X-Signature": sign_body(body)},
        timeout=10
    )
    response.raise_for_status()
    res: dict[str, Any] = response.json()
    return res

@celery.task
def process_individual(analysis_id: str, user_input: list[str]):
    result = individual(user_input)
    return call_frontend(
        f"/{getenv("INTERNAL_ROUTE", "internal")}/individual/success",
        {"analysis_id": analysis_id, "result": result}
    )