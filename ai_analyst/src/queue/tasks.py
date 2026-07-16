import hashlib
import hmac
import importlib
import json
from os import getenv
from typing import Any, Literal
import requests
from src.queue.celery_app import celery

def _load_main(type: Literal["individual", "comprehensive", "keyword_analysis", "resume"]):
    return importlib.import_module(f"src.ai.{type}").main

FRONTEND_API_URL = "http://app:8000"
INTERNAL_SECRET_KEY = "INTERNAL_SECRET"

def sign_body(body_bytes: bytes):
    key = getenv(INTERNAL_SECRET_KEY)
    if key is None:
        raise ValueError("Internal secret not set.")
    return hmac.new(key.encode(), body_bytes, hashlib.sha256).hexdigest()

def call_frontend(endpoint: str, body: dict[str, Any]):
    body_bytes = json.dumps(body, separators=(",", ":"), sort_keys=True, default=str).encode()
    response = requests.post(
        f"{FRONTEND_API_URL}{endpoint}",
        data=body_bytes,
        headers={"X-Signature": sign_body(body_bytes)},
        timeout=10
    )
    response.raise_for_status()
    res: dict[str, Any] = response.json()
    return res

@celery.task
def process_individual(analysis_id: str, user_input: list[str]):
    main = _load_main("individual")
    result = main(user_input)
    if not isinstance(result, dict) or result.get("status") != "success":
        return call_frontend(
            f"/{getenv("INTERNAL_ROUTE", "internal")}/individual/failure",
            {"analysis_id": analysis_id}
        )
    return call_frontend(
        f"/{getenv("INTERNAL_ROUTE", "internal")}/individual/success",
        {"analysis_id": analysis_id, "result": result}
    )

@celery.task
def process_comprehensive(analysis_id: str, user_input: list[str], school: str, department: str):
    main = _load_main("comprehensive")
    result = main(user_input, school, department)
    if not isinstance(result, dict) or result.get("status") != "success":
        return call_frontend(
            f"/{getenv("INTERNAL_ROUTE", "internal")}/comprehensive/failure",
            {"analysis_id": analysis_id}
        )
    return call_frontend(
        f"/{getenv("INTERNAL_ROUTE", "internal")}/comprehensive/success",
        {"analysis_id": analysis_id, "result": result}
    )

@celery.task
def process_keyword(analysis_id: str, user_input: str, keywords: list[str]):
    main = _load_main("keyword_analysis")
    result = main(keywords, user_input)
    if not isinstance(result, dict) or result.get("status") != "success":
        return call_frontend(
            f"/{getenv("INTERNAL_ROUTE", "internal")}/keyword/failure",
            {"analysis_id": analysis_id}
        )
    return call_frontend(
        f"/{getenv("INTERNAL_ROUTE", "internal")}/keyword/success",
        {"analysis_id": analysis_id, "result": result}
    )

@celery.task
def process_resume(
    resume_id: str,
    sources: list[str],
    name_ko: str = "",
    name_en: str = "",
    email: str = "",
    phone: str = "",
    school: str = "",
    department: str = "",
    links: str = "",
    language: str = "both",
):
    main = _load_main("resume")
    result = main(sources, name_ko, name_en, email, phone, school, department, links, language)
    return call_frontend(
        f"/{getenv("INTERNAL_ROUTE", "internal")}/resume/success",
        {"resume_id": resume_id, "result": result}
    )