from typing import Annotated
from src.queue.tasks import process_individual
# from src.comprehensive import main as comprehensive_main
# from src.resume import main as resume_main
from fastapi import Body, FastAPI

from src.models import ComprehensiveRequest, IndividualRequest, ResumeRequest

app = FastAPI()

@app.post("/individual")
async def individual(body: Annotated[IndividualRequest, Body()]):
    return process_individual(
        analysis_id = body.analysis_id,
        user_input = body.input
    )

# @app.post("/comprehensive")
# async def comprehensive(body: Annotated[ComprehensiveRequest, Body()]):
#     return comprehensive_main(body.input, body.school, body.department)

# @app.post("/resume")
# async def resume(body: Annotated[ResumeRequest, Body()]):
#     return resume_main(**body.model_dump())