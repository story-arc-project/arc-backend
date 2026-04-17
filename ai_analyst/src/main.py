from typing import Annotated
from src.queue.tasks import process_individual
from src.queue.tasks import process_comprehensive
# from src.resume import main as resume_main
from fastapi import Body, FastAPI, Response

from src.models import ComprehensiveRequest, IndividualRequest, ResumeRequest

app = FastAPI()

@app.post("/individual")
async def individual(body: Annotated[IndividualRequest, Body()], response: Response):
    task = process_individual.delay(str(body.analysis_id), body.input)
    response.status_code = 200
    return {
        "task_id": task.id
    }

@app.post("/comprehensive")
async def comprehensive(body: Annotated[ComprehensiveRequest, Body()], response: Response):
    task = process_comprehensive.delay(str(body.analysis_id), body.input, body.school, body.department)
    response.status_code = 200
    return {
        "task_id": task.id
    }

# @app.post("/resume")
# async def resume(body: Annotated[ResumeRequest, Body()]):
#     return resume_main(**body.model_dump())