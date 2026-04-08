from pydantic import BaseModel


class IndividualRequest(BaseModel):
    input: list[str]