from typing import Literal

ANALYSIS_TYPES = Literal["individual", "comprehensive", "keyword", "resume", "cover_letter"]

SCHEMA_VERSIONS: dict[ANALYSIS_TYPES, str] = {
    "comprehensive": "2.0",
    "individual": "1.2",
    "keyword": "4.1",
    "resume": "1.0",
    "cover_letter": "1.1"
}