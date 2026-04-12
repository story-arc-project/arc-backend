import hashlib
import hmac
import json
from os import getenv
from typing import Any
from celery import Task
import httpx
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
    # TODO: add logic
    response = httpx.post(
        f"{FRONTEND_API_URL}{endpoint}",
        json=body,
        headers={"X-Signature": sign_body(body)},
        timeout=10
    )
    response.raise_for_status()
    return response.json()

@celery.task(bind=True, max_retries=3, default_retry_delay=5)
def process_individual(self: Task, analysis_id: str, user_input: list[str]):
    try:
        result = individual(user_input)
        call_frontend(
            f"/{getenv("INTERNAL_ROUTE", "internal")}/individual/complete",
            {"analysis_id": analysis_id, "result": result}
        )

    except Exception as exc:
        raise self.retry(exc=exc)
