from typing import Annotated
from src.queue.tasks import process_comprehensive, process_individual, process_keyword, process_resume, process_cover_letter
# from src.resume import main as resume_main
from fastapi import Body, FastAPI, Response

from src.models import ComprehensiveRequest, IndividualRequest, KeywordRequest, ResumeRequest, CoverLetterRequest

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

@app.post("/keyword")
async def keyword(body: Annotated[KeywordRequest, Body()], response: Response):
    task = process_keyword.delay(str(body.analysis_id), body.input, body.keywords, body.target)
    response.status_code = 200
    return {
        "task_id": task.id
    }

@app.post("/resume")
async def resume(body: Annotated[ResumeRequest, Body()], response: Response):
    task = process_resume.delay(str(body.resume_id), body.sources, body.name_ko, "", body.email, body.phone, body.school, body.department, "", body.language)
    response.status_code = 200
    return {
        "task_id": task.id
    }

@app.post("/cover_letter")
async def cover_letter(body: Annotated[CoverLetterRequest, Body()], response: Response):
    task = process_cover_letter.delay(
        str(body.cover_letter_id),
        body.experiences,
        body.industry,
        body.name,
        body.target_company,
        body.target_job,
        body.school,
        body.department if body.department is not None else "",
        body.motivation,
        body.career_goal,
        body.extra_notes,
        body.questions
    )
    response.status_code = 200
    return {
        "task_id": task.id
    }

# @app.post("/resume")
# async def resume(body: Annotated[ResumeRequest, Body()]):
#     return resume_main(**body.model_dump())