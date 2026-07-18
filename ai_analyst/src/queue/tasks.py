import hashlib
import hmac
import json
from os import getenv
from typing import Any, Literal
import requests
from ..const import SCHEMA_VERSIONS
from src.queue.celery_app import celery

AnalysisTypes = Literal["individual", "comprehensive", "keyword", "resume"]

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

def call_failure(analysis_type: AnalysisTypes, analysis_id: str):
    return call_frontend(
        f"/{getenv("INTERNAL_ROUTE", "internal")}/{analysis_type}/failure",
        {"analysis_id": analysis_id}
    )

def call_success(analysis_type: AnalysisTypes, analysis_id: str, result: dict, vector: list[float] | None):
    body = {"analysis_id": analysis_id, "result": {**result, "schema_version": SCHEMA_VERSIONS[analysis_type]}, "vector": None}
    if vector:
        body["vector"] = vector
    return call_frontend(
        f"/{getenv("INTERNAL_ROUTE", "internal")}/{analysis_type}/success",
        body
    )

@celery.task
def process_individual(analysis_id: str, user_input: list[str]):
    from src.ai.individual import main as main_func
    analysis = main_func(
        user_input=user_input
    )
    if analysis.status == "error":
        return call_failure("individual", analysis_id)
    return call_success("individual", analysis_id, analysis.result, analysis.vector)

@celery.task
def process_comprehensive(analysis_id: str, user_input: list[str], school: str, department: str):
    from src.ai.comprehensive import main as main_func
    analysis = main_func(
        user_input=user_input,
        school=school,
        department=department
    )
    if analysis.status == "error":
        return call_failure("comprehensive", analysis_id)
    return call_success("comprehensive", analysis_id, analysis.result, analysis.vector)

@celery.task
def process_keyword(analysis_id: str, user_input: str, keywords: list[str], target: str):
    from src.ai.keyword_analysis import main as main_func
    analysis = main_func(
        career_input=user_input,
        keywords=keywords,
        target=target
    )
    if analysis.status == "error":
        return call_failure("keyword", analysis_id)
    return call_success("keyword", analysis_id, analysis.result, None)

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
    from src.ai.resume import main as main_func
    resume = main_func(
        sources=sources,
        name_ko=name_ko,
        name_en=name_en,
        email=email,
        phone=phone,
        school=school,
        department=department,
        links=links,
        language=language
    )
    if resume.status == "error":
        return call_failure("resume", resume_id)
    return call_success("resume", resume_id, resume.result, None)