from typing import Literal
from uuid import UUID
from pydantic import BaseModel


class IndividualRequest(BaseModel):
    analysis_id: UUID
    input: list[str]


class ComprehensiveRequest(BaseModel):
    analysis_id: UUID
    input: list[str]
    school: str
    department: str

class ResumeRequest(BaseModel):
    resume_id: UUID
    sources: list[str]
    name_ko: str
    email: str
    phone: str
    school: str
    department: str
    language: Literal["ko", "en", "both"]

class KeywordRequest(BaseModel):
    analysis_id: UUID
    input: str
    keywords: list[str]
    target: str

class CoverLetterRequest(BaseModel):
    cover_letter_id: UUID
    experiences: list[dict]
    name: str = ""
    target_company: str = ""
    target_job: str = ""
    school: str = ""
    department: str = ""
    motivation: str = ""
    career_goal: str = ""
    extra_notes: str = ""
    questions: list[dict] | None = None