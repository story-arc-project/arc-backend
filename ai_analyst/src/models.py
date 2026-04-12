from typing import Literal
from uuid import UUID
from pydantic import BaseModel


class IndividualRequest(BaseModel):
    analysis_id: UUID
    input: list[str]


class ComprehensiveRequest(BaseModel):
    input: list[str]
    school: str
    department: str

class ResumeRequest(BaseModel):
    sources: list[str]
    name_ko: str
    name_en: str
    email: str
    phone: str
    school: str
    department: str
    links: str
    language: Literal["ko", "en", "both"]
    output_path: str
    deep_crawl: bool