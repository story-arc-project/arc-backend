from pydantic import BaseModel


class IndividualRequest(BaseModel):
    input: list[str]


class ComprehensiveRequest(BaseModel):
    input: list[str]
    school: str
    department: str