from typing import Annotated
from src.individual import main
from fastapi import Body, FastAPI

from src.models import IndividualRequest

app = FastAPI()

@app.post("/individual")
async def individual(body: Annotated[IndividualRequest, Body()]):
    return main(body.input)