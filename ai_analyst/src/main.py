from typing import Annotated
from src.individual import main as individual_main
from src.comprehensive import main as comprehensive_main
from fastapi import Body, FastAPI

from src.models import ComprehensiveRequest, IndividualRequest

app = FastAPI()

@app.post("/individual")
async def individual(body: Annotated[IndividualRequest, Body()]):
    return individual_main(body.input)

@app.post("/comprehensive")
async def comprehensive(body: Annotated[ComprehensiveRequest, Body()]):
    return comprehensive_main(body.input, body.school, body.department)