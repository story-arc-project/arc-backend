import hashlib
import hmac
import json
from os import getenv
from typing import Any, Literal
import requests
from ..const import SCHEMA_VERSIONS
from src.queue.celery_app import celery
import traceback

AnalysisTypes = Literal["individual", "comprehensive", "keyword", "resume", "cover_letter"]

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
    body = {"analysis_id": analysis_id, "result": {**result, "schema_version": f"{analysis_type}/{SCHEMA_VERSIONS[analysis_type]}"}, "vector": None}
    if vector:
        body["vector"] = vector
    return call_frontend(
        f"/{getenv("INTERNAL_ROUTE", "internal")}/{analysis_type}/success",
        body
    )

@celery.task
def process_individual(analysis_id: str, user_input: list[str]):
    try:
        from src.ai.individual import main as main_func
        analysis = main_func(
            user_input=user_input
        )
        if analysis.status == "error":
            return call_failure("individual", analysis_id)
        return call_success("individual", analysis_id, analysis.result, analysis.vector)
    except:
        traceback.print_exc()
        return call_failure("individual", analysis_id)

@celery.task
def process_comprehensive(analysis_id: str, user_input: list[str], school: str, department: str):
    try:
        from src.ai.comprehensive import main as main_func
        analysis = main_func(
            user_input=user_input,
            school=school,
            department=department
        )
        if analysis.status == "error":
            return call_failure("comprehensive", analysis_id)
        return call_success("comprehensive", analysis_id, analysis.result, analysis.vector)
    except:
        traceback.print_exc()
        return call_failure("comprehensive", analysis_id)

@celery.task
def process_keyword(analysis_id: str, user_input: str, keywords: list[str], target: str):
    try:
        from src.ai.keyword_analysis import main as main_func
        analysis = main_func(
            career_input=user_input,
            keywords=keywords,
            target=target
        )
        if analysis.status == "error":
            return call_failure("keyword", analysis_id)
        return call_success("keyword", analysis_id, analysis.result, None)
    except:
        traceback.print_exc()
        return call_failure("keyword", analysis_id)

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
    try:
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
    except:
        traceback.print_exc()
        return call_failure("resume", resume_id)

@celery.task
def process_cover_letter(
    cover_letter_id: str,
    experiences: list[dict],
    name: str = "",
    target_company: str = "",
    target_job: str = "",
    school: str = "",
    department: str = "",
    motivation: str = "",
    career_goal: str = "",
    extra_notes: str = "",
    questions: list[dict] | None = None,
    job_key: str = "",
    region: str = "KR",
):
    try:
        from src.ai.cover_letter import main as main_func, UserProfile

        bucketed: dict[str, list] = {}
        for exp in experiences:
            bucketed.setdefault(exp["type"], []).append(exp["content"])

        user = UserProfile(
            name=name,
            target_company=target_company,
            target_job=target_job,
            education=[{"school": school, "major": department}] if school or department else [],
            experiences=bucketed.get("experience", []),
            projects=bucketed.get("project", []),
            skills=bucketed.get("skill", []),
            certifications=bucketed.get("certification", []),
            awards=bucketed.get("award", []),
            activities=bucketed.get("activity", []),
            achievements=bucketed.get("achievement", []),
            strengths=bucketed.get("strength", []),
            motivation=motivation,
            career_goal=career_goal,
            extra_notes=extra_notes,
        )

        response = main_func(
            user=user,
            job_key=job_key,
            region=region,
            questions=questions or [],
        )

        if response.status == "error":
            return call_failure("cover_letter", cover_letter_id)
        return call_success("cover_letter", cover_letter_id, response.result, None)
    except:
        traceback.print_exc()
        return call_failure("cover_letter", cover_letter_id)