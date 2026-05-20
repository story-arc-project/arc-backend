from typing import Annotated
from src.queue.tasks import process_comprehensive, process_individual, process_keyword, process_resume
# from src.resume import main as resume_main
from fastapi import Body, FastAPI, Response, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
import logging

from src.models import ComprehensiveRequest, IndividualRequest, KeywordRequest, ResumeRequest

logger = logging.getLogger("ai_analyst")
logging.basicConfig(level=logging.INFO)

app = FastAPI()


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # Log the validation errors and return them in the response with 422 status
    logger.error("Validation error on %s: %s", request.url.path, exc.errors())
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


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

@app.post("/keyword")
async def keyword(body: Annotated[KeywordRequest, Body()], response: Response):
    task = process_keyword.delay(str(body.analysis_id), body.input, body.keywords)
    response.status_code = 200
    return {
        "task_id": task.id
    }

@app.post("/resume")
async def resume(body: Annotated[ResumeRequest, Body()], response: Response):
    task = process_resume.delay(body.resume_id, body.sources, body.name_ko, body.email, body.phone, body.school, body.department, body.language)
    response.status_code = 200
    return {
        "task_id": task.id
    }

# @app.post("/resume")
# async def resume(body: Annotated[ResumeRequest, Body()]):
#     return resume_main(**body.model_dump())